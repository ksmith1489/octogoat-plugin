#!/usr/bin/env python3
from __future__ import annotations

"""
lazarus_web.py

Single-file Flask app: generate a "resume" G-code safely, using ONLY:
  - Layer Height (LH)
  - Measured Print Height (PH)
"""

from werkzeug.middleware.proxy_fix import ProxyFix
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import io
import os
import re
import secrets
import time

from flask import (
    Flask,
    request,
    jsonify,
    render_template_string,
    send_file,
    redirect,
    url_for,
    flash,
    Response,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# ===================== WEB UI =====================
HTML_PAGE = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Lazarus – Print Resurrection Lab</title>

  <script>
    window.memberstackConfig = { useCookies: true, setCookieOnRootDomain: true };
  </script>
  <script
    data-memberstack-app="app_cmjfk6pl8005z0tsh0b64027x"
    src="https://static.memberstack.com/scripts/v2/memberstack.js"
    type="text/javascript">
  </script>

  <style>
    #app-content { visibility: hidden; }
    .ms-member #app-content { visibility: visible; }

    body { font-family:sans-serif; background:#111; color:#eee; padding:20px; }
    h1 { margin:0 0 4px 0; }
    small { color:#aaa; }
    .card { background:#1b1b1b; padding:15px 20px; border-radius:10px; max-width:920px; }
    label { display:block; margin-top:10px; }
    input, select, textarea {
      background:#222; color:#eee; border:1px solid #444; border-radius:6px;
      padding:6px; margin-top:4px;
    }
    textarea { width:100%; min-height:80px; }
    .row { display:flex; gap:16px; flex-wrap:wrap; margin-top:8px; }
    .btn { margin-top:14px; padding:10px 16px; background:#3a7; border:none; color:#fff;
           border-radius:8px; cursor:pointer; font-weight:bold; }
    .btn:hover { background:#4b8; }
    .btn2 { margin-top:14px; padding:10px 16px; background:#345; border:none; color:#fff;
            border-radius:8px; cursor:pointer; font-weight:bold; }
    .btn2:hover { background:#456; }
    .danger { color:#f66; font-size:0.95em; }
    pre { background:#0d0d0d; border:1px solid #333; padding:10px; border-radius:10px; overflow:auto; }
    hr { border-color:#333; margin:14px 0; }

    #topbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
    #account-panel, #cancel-modal { display:none; background:#1b1b1b; padding:16px; border-radius:10px; margin-top:12px; }
  </style>

  <script>
    let CURRENT_MEMBER = null;

    window.addEventListener("load", () => {
      const loginRedirect = "https://lazarus3dprint.com/free-iq-test";
      let tries = 0;

      const timer = setInterval(async () => {
        tries++;
        const ms = window.$memberstackDom;
        if (!ms?.getCurrentMember) return;

        const res = await ms.getCurrentMember();
        const member = res?.data || null;

        if (member) {
          CURRENT_MEMBER = member;
          document.documentElement.classList.add("ms-member");
          clearInterval(timer);
          populateAccount();
          return;
        }

        if (tries > 80) window.location.href = loginRedirect;
      }, 200);
    });

    function populateAccount() {
      if (!CURRENT_MEMBER) return;
      document.getElementById("acct-email").textContent = CURRENT_MEMBER.email;
      document.getElementById("acct-plan").textContent =
        CURRENT_MEMBER.planConnections?.[0]?.planName || "Unknown";
    }

    function toggleAccount() {
      const p = document.getElementById("account-panel");
      p.style.display = p.style.display === "none" ? "block" : "none";
    }

    function openCancel() {
      document.getElementById("cancel-modal").style.display = "block";
    }

    async function submitCancel() {
      const payload = {
        email: CURRENT_MEMBER.email,
        member_id: CURRENT_MEMBER.id,
        plan: CURRENT_MEMBER.planConnections?.[0]?.planName,
        reason: document.getElementById("cancel-reason").value,
        details: document.getElementById("cancel-details").value
      };

      await fetch("/cancel-request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      alert("Cancellation request received. We’ll follow up shortly.");
      document.getElementById("cancel-modal").style.display = "none";
    }
  </script>
</head>

<body>
<div id="app-content">

  <div id="topbar">
    <div>
      <h1>Lazarus</h1>
      <small>Two-input build: layer height + print height</small>
    </div>
    <button class="btn2" onclick="toggleAccount()">Account</button>
  </div>

  <div id="account-panel">
    <p><b>Email:</b> <span id="acct-email"></span></p>
    <p><b>Plan:</b> <span id="acct-plan"></span></p>
    <button class="btn" onclick="openCancel()">Cancel Subscription</button>
  </div>

  <div id="cancel-modal">
    <h3>Before you cancel</h3>
    <select id="cancel-reason">
      <option>Did not work as expected</option>
      <option>Too complicated</option>
      <option>Compatibility issue</option>
      <option>No longer needed</option>
      <option>Other</option>
    </select>
    <textarea id="cancel-details" placeholder="Briefly explain what happened"></textarea>
    <button class="btn" onclick="submitCancel()">Submit request</button>
  </div>

</div>
</body>
</html>
"""


# ===================== FLASK APP =====================
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour"],
)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-secret")


@app.route("/robots.txt")
def robots():
    return Response(
        """User-agent: *
Disallow: /app/
""",
        mimetype="text/plain",
    )


MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

GEN_DIR = Path(os.environ.get("LAZARUS_GEN_DIR", "/tmp/lazarus_generated"))
GEN_DIR.mkdir(parents=True, exist_ok=True)

GENERATED: Dict[str, Dict[str, object]] = {}
GENERATED_TTL_SECONDS = 20 * 60

DEFAULT_Z_MATCH_TOL = 0.05
DEFAULT_Z_FLOOR_TOL = 0.05


@app.errorhandler(413)
def _too_large(_e):
    flash(f"File too large. Max upload is {MAX_UPLOAD_MB} MB.")
    return redirect(url_for("index"))


# ===================== ROUTES =====================

@app.route("/", methods=["GET", "POST"])
@app.route("/app", methods=["GET", "POST"])
def index():
    _cleanup_generated()

    if request.method == "GET":
        return render_template_string(
            HTML_PAGE,
            preview=None,
            token=None,
            preview_lines=220,
            resume_z=None,
            form={
                "firmware": "klipper",
                "layer_height": "",
                "print_height": "",
                "z_match_tol": "0.05",
                "z_floor_tol": "0.05",
                "inject_f": True,
                "user_msgs": True,
            },
        )

    file = request.files.get("gcode_file")
    if not file or file.filename == "":
        flash("Please upload a G-code file.")
        return redirect(url_for("index"))

    original_text = file.read().decode("utf-8", errors="ignore")
    if not original_text.strip():
        flash("Uploaded file is empty or unreadable.")
        return redirect(url_for("index"))

    form_state = {
        "firmware": (request.form.get("firmware") or "klipper").strip().lower(),
        "layer_height": request.form.get("layer_height", ""),
        "print_height": request.form.get("print_height", ""),
        "z_match_tol": request.form.get("z_match_tol", "0.05"),
        "z_floor_tol": request.form.get("z_floor_tol", "0.05"),
        "inject_f": (request.form.get("inject_f") in ("1", "on", "true", "True")),
        "user_msgs": (request.form.get("user_msgs") in ("1", "on", "true", "True")),
    }

    layer_h = float(form_state["layer_height"])
    print_h = float(form_state["print_height"])

    token = secrets.token_urlsafe(16)
    out_path = str(GEN_DIR / f"{token}.gcode")

    resume_z, preview = build_resumed_gcode_to_file(
        original_gcode_text=original_text,
        firmware=form_state["firmware"],
        layer_height_mm=layer_h,
        print_height_mm=print_h,
        z_match_tol=float(form_state["z_match_tol"]),
        z_floor_tol=float(form_state["z_floor_tol"]),
        inject_last_motion_feedrate=form_state["inject_f"],
        include_user_check_messages=form_state["user_msgs"],
        out_path=out_path,
        preview_lines=220,
    )

    GENERATED[token] = {
        "path": out_path,
        "name": f"LAZARUS_RH_{resume_z:.3f}.gcode",
        "ts": time.time(),
    }

    return render_template_string(
        HTML_PAGE,
        preview=preview,
        token=token,
        preview_lines=220,
        resume_z=f"{resume_z:.3f}",
        form=form_state,
    )


@app.route("/cancel-request", methods=["POST"])
def cancel_request():
    data = request.get_json(silent=True) or {}
    print("CANCEL REQUEST:", data)
    return jsonify({"status": "ok"})


def _cleanup_generated():
    now = time.time()
    for k in list(GENERATED.keys()):
        if now - GENERATED[k]["ts"] > GENERATED_TTL_SECONDS:
            try:
                Path(GENERATED[k]["path"]).unlink(missing_ok=True)
            except Exception:
                pass
            GENERATED.pop(k, None)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
