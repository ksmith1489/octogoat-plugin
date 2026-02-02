#!/usr/bin/env python3
from __future__ import annotations

"""
lazarus_web.py

Single-file Flask app: generate a "resume" G-code safely, using ONLY:
  - Layer Height (LH)
  - Measured Print Height (PH)

Run locally:
  pip install flask
  python lazarus_web.py
Open:
  http://127.0.0.1:5000
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
    request, jsonify
    render_template_string,
    send_file,
    redirect,
    url_for,
    flash,
    Response
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ===================== WEB UI =====================
HTML_PAGE = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Lazarus – Print Resurrection Lab</title>

  <!-- Memberstack v2 -->
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

    /* Account UI */
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

  <!-- YOUR EXISTING FORM / PREVIEW CONTENT CONTINUES BELOW UNCHANGED -->

</div>
</body>
</html>
"""

# ===================== FLASK + CORE LOGIC =====================

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour"]
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-secret")
@app.route("/robots.txt")
def robots():
    return Response(
    
       """User-agent: *
Disallow: /app/

User-agent: DotBot
Disallow: /

User-agent: air.ai
Disallow: /
""",
        mimetype="text/plain"
    )

# Hard cap uploads so one big G-code can't OOM the server.
# You can change via Render env var: MAX_UPLOAD_MB
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024  # enforced by Werkzeug

# Store generated files on disk (NOT in RAM)
GEN_DIR = Path(os.environ.get("LAZARUS_GEN_DIR", "/tmp/lazarus_generated"))
GEN_DIR.mkdir(parents=True, exist_ok=True)

# token -> {"path": str, "name": str, "ts": float}
GENERATED: Dict[str, Dict[str, object]] = {}
GENERATED_TTL_SECONDS = 20 * 60  # 20 minutes

DEFAULT_Z_MATCH_TOL = 0.05
DEFAULT_Z_FLOOR_TOL = 0.05


@app.errorhandler(413)
def _too_large(_e):
    flash(f"File too large. Max upload is {MAX_UPLOAD_MB} MB.")
    return redirect(url_for("index"))


@app.before_request
def _log_req():
    ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP")
        or request.remote_addr
    )
    ua = request.headers.get("User-Agent", "")
    path = request.path
    ref = request.headers.get("Referer", "")
    print(f"REQ ip={ip} path={path} ua={ua} ref={ref}", flush=True)


# ---- Core parsing helpers (kept) ----

@dataclass
class AnchorResult:
    anchor_index: int
    resume_z: float
    detected_e_mode: str  # "absolute" or "relative"
    last_e_abs: float
    last_motion_f: Optional[float]


def _strip_comment(line: str) -> str:
    return line.split(";", 1)[0].strip()


def _extract_float_param(line: str, letter: str) -> Optional[float]:
    if not line:
        return None
    code = line.split(";", 1)[0]
    m = re.search(rf"(?i)(?:^|\s){re.escape(letter)}\s*(?:=\s*)?([-+]?\d*\.?\d+)", code)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _is_motion(line: str) -> bool:
    s = line.lstrip().upper()
    return s.startswith("G0") or s.startswith("G1") or s.startswith("G2") or s.startswith("G3")


def is_real_printing_move(line: str) -> bool:
    if not _is_motion(line):
        return False
    e = _extract_float_param(line, "E")
    if e is None:
        return False
    x = _extract_float_param(line, "X")
    y = _extract_float_param(line, "Y")
    return (x is not None) or (y is not None)


def _extract_z_comment(line: str) -> Optional[float]:
    if not line:
        return None
    m = re.search(r"(?i)^\s*;\s*Z\s*:\s*([-+]?\d*\.?\d+)\s*$", line.strip())
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def should_strip_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    up = s.upper()

    if up.startswith("G28") or up.startswith("G29") or up.startswith("G34"):
        return True
    if "BED_MESH_CALIBRATE" in up or "Z_TILT_ADJUST" in up:
        return True

    if up.startswith("START_PRINT") or up.startswith("PRINT_START"):
        return True
    if up.startswith("END_PRINT") or up.startswith("PRINT_END"):
        return True
    if up.startswith("CANCEL_PRINT"):
        return True

    if "SAVE_GCODE_STATE" in up or "RESTORE_GCODE_STATE" in up:
        return True

    return False


def infer_resume_z(print_height_mm: float, layer_height_mm: float) -> float:
    if layer_height_mm <= 0:
        raise ValueError("Layer height must be > 0.")
    if print_height_mm < 0:
        raise ValueError("Print height must be >= 0.")
    k = int(round(print_height_mm / layer_height_mm))
    return max(0.0, k * layer_height_mm)


def _replace_e_value(line: str, new_e: float) -> str:
    if ";" in line:
        code_part, comment = line.split(";", 1)
        comment = ";" + comment
    else:
        code_part, comment = line, ""

    def repl(m: re.Match) -> str:
        return f"{m.group(1)}{new_e:.5f}"

    new_code = re.sub(
        r"(?i)(\bE\s*)(?:=\s*)?([-+]?\d*\.?\d+)",
        repl,
        code_part,
        count=1,
    ).rstrip()

    if comment:
        if not new_code.endswith(" "):
            new_code += " "
        new_code += comment.lstrip()
    return new_code


# ===================== LEAN MEMORY GENERATION =====================

def build_resumed_gcode_to_file(
    original_gcode_text: str,
    *,
    firmware: str,
    layer_height_mm: float,
    print_height_mm: float,
    out_path: str,
    z_match_tol: float = DEFAULT_Z_MATCH_TOL,
    z_floor_tol: float = DEFAULT_Z_FLOOR_TOL,
    inject_last_motion_feedrate: bool = True,
    include_user_check_messages: bool = True,  # kept for API compatibility (unused here)
    preview_lines: int = 220,
) -> Tuple[float, str]:
    """
    Writes resumed G-code directly to out_path (disk), returns (resume_z, preview_text).
    Designed to avoid large in-RAM copies.
    """
    resume_z = infer_resume_z(print_height_mm=print_height_mm, layer_height_mm=layer_height_mm)
    z_floor = resume_z - float(z_floor_tol)

    # PASS 1: Find anchor index + track extrusion mode, last absolute E, and last motion feedrate
    detected_mode = "absolute"
    last_e_abs = 0.0
    last_motion_f: Optional[float] = None
    current_z: Optional[float] = None
    anchor_index: Optional[int] = None

    for i, raw in enumerate(io.StringIO(original_gcode_text)):
        zc = _extract_z_comment(raw)
        if zc is not None:
            current_z = float(zc)

        code = _strip_comment(raw)
        up = code.upper() if code else ""

        # Track extrusion mode & absolute E state
        if up.startswith("M82"):
            detected_mode = "absolute"
        elif up.startswith("M83"):
            detected_mode = "relative"
        elif up.startswith("G92"):
            e = _extract_float_param(code, "E")
            if e is not None:
                last_e_abs = float(e)
        elif _is_motion(code) and detected_mode == "absolute":
            e = _extract_float_param(code, "E")
            if e is not None:
                last_e_abs = float(e)

        # Track Z/F from motion lines
        if _is_motion(raw):
            z = _extract_float_param(raw, "Z")
            if z is not None:
                current_z = float(z)

            f = _extract_float_param(raw, "F")
            if f is not None:
                last_motion_f = float(f)

        # Anchor condition
        if current_z is not None and current_z >= (resume_z - z_match_tol):
            if not should_strip_line(raw) and is_real_printing_move(raw):
                anchor_index = i
                break

    if anchor_index is None:
        raise ValueError("Could not find a resume anchor at/after computed resume height.")

    # Build header (small, safe)
    header: List[str] = []
    header.append("; --- RESUME FROM FAILURE (LAZARUS) ---")
    header.append(f"; Inputs: LH={layer_height_mm:.5f}mm, PH={print_height_mm:.3f}mm")
    header.append(f"; Computed resume height (RH): {resume_z:.3f} mm (nearest multiple of LH)")
    header.append(f"; Anchor index: {anchor_index}")
    header.append(f"; Z-match tol: {z_match_tol:.3f} mm | Z-floor guard: Z >= {z_floor:.3f} mm")
    header.append(f"; Detected extrusion mode in source: {detected_mode.upper()}")
    header.append("G90 ; absolute positioning")
    header.append("G21 ; millimeters")
    header.append("M83 ; relative extrusion (Lazarus-safe)")
    header.append("G92 E0 ; reset extruder")

    if inject_last_motion_feedrate and last_motion_f is not None:
        header.append(f"G1 F{last_motion_f:.3f} ; inherit slicer feedrate before anchor")

    header.append("; --- BEGIN RESUMED TOOLPATH ---")

    # Preview buffer (tiny, bounded)
    preview_buf: List[str] = []
    preview_count = 0

    def _preview_add(line_with_nl: str) -> None:
        nonlocal preview_count
        if preview_count < preview_lines:
            preview_buf.append(line_with_nl.rstrip("\n"))
            preview_count += 1

    # PASS 2: stream write from anchor onward, filtering and converting E if needed
    cur_abs_e = float(last_e_abs)

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for ln in header:
            f.write(ln + "\n")
            _preview_add(ln + "\n")

        for i, raw in enumerate(io.StringIO(original_gcode_text)):
            if i < anchor_index:
                continue

            if should_strip_line(raw):
                continue

            if _is_motion(raw):
                z = _extract_float_param(raw, "Z")
                if z is not None and float(z) < z_floor:
                    continue

            out_line = raw.rstrip("\n")

            # Convert absolute E -> relative E on the fly
            if detected_mode == "absolute":
                code = _strip_comment(out_line)
                up = code.upper() if code else ""

                if up.startswith("G92"):
                    e = _extract_float_param(code, "E")
                    if e is not None:
                        cur_abs_e = float(e)
                        out_line = "G92 E0"
                elif _is_motion(code):
                    e_abs = _extract_float_param(code, "E")
                    if e_abs is not None:
                        e_abs = float(e_abs)
                        e_rel = e_abs - cur_abs_e
                        cur_abs_e = e_abs
                        out_line = _replace_e_value(out_line, e_rel)

            f.write(out_line + "\n")
            _preview_add(out_line + "\n")

        f.write("; --- END RESUMED FILE ---\n")
        _preview_add("; --- END RESUMED FILE ---\n")

    return resume_z, "\n".join(preview_buf)


def _cleanup_generated() -> None:
    now = time.time()
    dead: List[str] = []

    for k, v in list(GENERATED.items()):
        ts = float(v.get("ts", 0.0))
        if now - ts > GENERATED_TTL_SECONDS:
            dead.append(k)

    for k in dead:
        rec = GENERATED.pop(k, None)
        if not rec:
            continue
        p = rec.get("path")
        if p:
            try:
                Path(str(p)).unlink(missing_ok=True)
            except Exception:
                pass


# ===================== ROUTES =====================

@app.route("/", methods=["GET", "POST"])
@app.route("/app", methods=["GET", "POST"])
@app.route("/cancel-request", methods=["POST"])
@app.route("/cancel-request", methods=["POST"])
def cancel_request():
    data = request.get_json(silent=True) or {}
    print("CANCEL REQUEST:", data)
    return jsonify({"status": "ok"})

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

    # Read upload (MAX_CONTENT_LENGTH already enforced). Still decode once.
    try:
        raw_bytes = file.read()
        original_text = raw_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        flash(f"Could not read file: {e}")
        return redirect(url_for("index"))

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

    try:
        layer_h = float(str(form_state["layer_height"]).strip())
        print_h = float(str(form_state["print_height"]).strip())
        z_match_tol = float(str(form_state["z_match_tol"]).strip() or "0.05")
        z_floor_tol = float(str(form_state["z_floor_tol"]).strip() or "0.05")
    except Exception:
        flash("Invalid numeric input. Check layer height / print height / tolerances.")
        return redirect(url_for("index"))

    if layer_h <= 0:
        flash("Layer height must be > 0.")
        return redirect(url_for("index"))
    if print_h < 0:
        flash("Print height must be >= 0.")
        return redirect(url_for("index"))

    if z_match_tol < 0:
        z_match_tol = DEFAULT_Z_MATCH_TOL
    if z_floor_tol < 0:
        z_floor_tol = DEFAULT_Z_FLOOR_TOL

    token = secrets.token_urlsafe(16)
    base_name = os.path.splitext(file.filename or "resume")[0]
    out_path = str(GEN_DIR / f"{token}.gcode")

    try:
        resume_z, preview = build_resumed_gcode_to_file(
            original_gcode_text=original_text,
            firmware=form_state["firmware"],
            layer_height_mm=layer_h,
            print_height_mm=print_h,
            z_match_tol=z_match_tol,
            z_floor_tol=z_floor_tol,
            inject_last_motion_feedrate=bool(form_state["inject_f"]),
            include_user_check_messages=bool(form_state["user_msgs"]),
            out_path=out_path,
            preview_lines=220,
        )
    except Exception as e:
        # Clean temp output if it exists
        try:
            Path(out_path).unlink(missing_ok=True)
        except Exception:
            pass
        flash(f"Error generating recovery G-code: {e}")
        return redirect(url_for("index"))

    out_name = f"{base_name}_LAZARUS_RH_{resume_z:.3f}.gcode"
    GENERATED[token] = {"path": out_path, "name": out_name, "ts": time.time()}

    return render_template_string(
        HTML_PAGE,
        preview=preview,
        token=token,
        preview_lines=220,
        resume_z=f"{resume_z:.3f}",
        form=form_state,
    )


@app.route("/download/<token>")
def download(token: str):
    _cleanup_generated()
    rec = GENERATED.get(token)
    if not rec:
        flash("That download token expired. Generate again.")
        return redirect(url_for("index"))

    p = rec.get("path")
    if not p or not os.path.exists(str(p)):
        flash("That download token expired. Generate again.")
        return redirect(url_for("index"))

    return send_file(
        str(p),
        mimetype="text/plain",
        as_attachment=True,
        download_name=str(rec["name"]),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
