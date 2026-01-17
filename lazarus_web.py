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

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import io
import os
import re
import secrets
import time

from flask import Flask, request, render_template_string, send_file, redirect, url_for, flash


# ===================== WEB UI =====================
HTML_PAGE = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Lazarus – Print Resurrection Lab</title>

  <!-- Memberstack v2 (IMPORTANT: must be window.memberstackConfig, not const) -->
  <script>
    window.memberstackConfig = { useCookies: true, setCookieOnRootDomain: true };
  </script>
  <script
    data-memberstack-app="app_cmjfk6pl8005z0tsh0b64027x"
    src="https://static.memberstack.com/scripts/v2/memberstack.js"
    type="text/javascript">
  </script>

  <style>
    /* 🔒 Gate: hide app until member is confirmed */
    #app-content { visibility: hidden; }
    .ms-member #app-content { visibility: visible; }

    body { font-family: sans-serif; background:#111; color:#eee; padding:20px; }
    h1 { margin: 0 0 4px 0; }
    small { color:#aaa; }
    .card { background:#1b1b1b; padding:15px 20px; border-radius:10px; max-width:920px; }
    label { display:block; margin-top:10px; }
    input[type=number], input[type=password], select {
      width: 280px; padding:6px; margin-top:4px; background:#222; color:#eee;
      border:1px solid #444; border-radius:6px;
    }
    input[type=file] { margin-top:6px; }
    .row { display:flex; gap:16px; flex-wrap:wrap; margin-top:8px; }
    .btn { margin-top:14px; padding:10px 16px; background:#3a7; border:none; color:#fff;
           border-radius:8px; cursor:pointer; font-weight:bold; }
    .btn:hover { background:#4b8; }
    .btn2 { margin-top:14px; padding:10px 16px; background:#345; border:none; color:#fff;
           border-radius:8px; cursor:pointer; font-weight:bold; text-decoration:none; display:inline-block; }
    .btn2:hover { background:#456; }
    .flash { background:#662222; padding:10px 12px; border-radius:8px; margin-bottom:10px; }
    pre { background:#0d0d0d; border:1px solid #333; padding:10px; border-radius:10px; overflow:auto; max-height:460px; }
    hr { border-color:#333; margin:14px 0; }
    .danger { color:#f66; font-size:0.95em; }
    details { margin-top:10px; }
    code { background:#222; padding:2px 6px; border-radius:6px; border:1px solid #333; }
  </style>
<script>
  window.addEventListener("load", () => {
    const debug = new URLSearchParams(location.search).get("debug") === "1";
    const loginRedirect = "https://lazarus3dprint.com/free-iq-test";
    const REQUIRE_PERMISSION = "paid"; // <-- your Memberstack permission name

    function log(...args) { if (debug) console.log(...args); }

    // normalize statuses to uppercase strings
    function normStatus(s) {
      return (s == null) ? "" : String(s).trim().toUpperCase();
    }

    function hasAccess(member) {
      if (!member) return false;

      // 1) BEST: permission gate (you already have permissions: ["paid"])
      const perms = Array.isArray(member.permissions) ? member.permissions : [];
      if (REQUIRE_PERMISSION && perms.includes(REQUIRE_PERMISSION)) return true;

      // 2) Fallback: planConnections statuses (your data lives here)
      const pcs = Array.isArray(member.planConnections) ? member.planConnections : [];
      const ok = new Set(["ACTIVE", "TRIALING", "TRIAL", "PAID"]);
      if (pcs.some(pc => ok.has(normStatus(pc?.status)))) return true;

      // 3) Optional extra fallback if Memberstack ever starts returning plans again
      const plans = Array.isArray(member.plans) ? member.plans : [];
      if (plans.some(p => ok.has(normStatus(p?.status)))) return true;

      return false;
    }

    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;

      const ms = window.$memberstackDom;
      if (!ms?.getCurrentMember) {
        if (tries > 80) { // ~16s
          clearInterval(timer);
          log("[MS] never became ready on app domain");
          if (!debug) window.location.href = loginRedirect;
        }
        return;
      }

      try {
        const res = await ms.getCurrentMember();
        const member = res?.data || null;
        log("[MS] getCurrentMember:", res);

        if (member) {
          if (hasAccess(member)) {
            clearInterval(timer);
            document.documentElement.classList.add("ms-member");
            log("[MS] access confirmed ✅ (unlocked)");
            return;
          }

          log("[MS] logged in but NO access -> redirect");
          if (!debug) window.location.href = loginRedirect;
          return;
        }

        // Not logged in yet -> open login modal ONCE, but keep polling
        log("[MS] not logged in -> open login modal");
        if (!window.__msLoginModalOpened && ms.openModal) {
          window.__msLoginModalOpened = true;
          ms.openModal("LOGIN");
        }
        return;

      } catch (e) {
        clearInterval(timer);
        log("[MS] error:", e);
        if (window.$memberstackDom?.openModal) window.$memberstackDom.openModal("LOGIN");
        if (!debug) window.location.href = loginRedirect;
      }
    }, 200);
  });
</script>


   

 

</head>

<body>
  <!-- EVERYTHING you want hidden MUST be inside this div -->
  <div id="app-content">
    <h1>Lazarus</h1>
    <small>Two-input build: layer height + print height</small>
    <br><br>

    <div class="card">
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          {% for m in messages %}
            <div class="flash">{{ m }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}

      <form method="post" enctype="multipart/form-data">
        <label>Original G-code file:
          <input type="file" name="gcode_file" required>
        </label>

        <div class="row">
          <label>Firmware:
            <select name="firmware">
              <option value="klipper" {% if form.firmware=='klipper' %}selected{% endif %}>Klipper</option>
              <option value="marlin"  {% if form.firmware=='marlin' %}selected{% endif %}>Marlin</option>
            </select>
          </label>
        </div>

        <hr>

        <div class="row">
          <label>Layer height (mm):
            <input type="number" step="0.001" name="layer_height" value="{{ form.layer_height or '' }}" required>
          </label>
          <label>Measured print height (mm):
            <input type="number" step="0.01" name="print_height" value="{{ form.print_height or '' }}" required>
          </label>
        </div>

        <div class="row">
          <label>Z match tolerance (mm) (default {{ form.z_match_tol or '0.05' }}):
            <input type="number" step="0.01" name="z_match_tol" value="{{ form.z_match_tol or '0.05' }}">
          </label>
          <label>Z floor guard (mm) (default {{ form.z_floor_tol or '0.05' }}):
            <input type="number" step="0.01" name="z_floor_tol" value="{{ form.z_floor_tol or '0.05' }}">
          </label>
        </div>

        <div class="row">
          <label>
            <input type="checkbox" name="inject_f" value="1" {% if form.inject_f %}checked{% endif %}>
            Inherit slicer feedrate near anchor (recommended)
          </label>
          <label>
            <input type="checkbox" name="user_msgs" value="1" {% if form.user_msgs %}checked{% endif %}>
            Add short console checklist (recommended)
          </label>
        </div>

        <div class="danger" style="margin-top:8px;">
          Read and follow instructions before generating the resumed file.
        </div>

        <button class="btn" type="submit">Preview + Generate</button>
      </form>

      {% if preview %}
        <hr>
        <h3 style="margin:0 0 6px 0;">Preview (first {{ preview_lines }} lines)</h3>
        <div style="color:#aaa; margin-bottom:10px;">
          Computed RH: <b>{{ resume_z }}</b> mm
        </div>
        <pre>{{ preview }}</pre>

        {% if token %}
          <a class="btn2" href="{{ url_for('download', token=token) }}">Download resumed G-code</a>
        {% endif %}
      {% endif %}

      <hr>
      <details>
        <summary style="cursor:pointer; color:#aaa; font-weight:bold;">Measuring tip (fast + accurate)</summary>
        <div style="margin-top:10px; color:#ddd; line-height:1.45;">
          Home Z normally (bed as truth), then jog Z up to the top of the print and read the Z value.
          Enter that as <code>Measured print height</code>. Lazarus rounds to the nearest multiple of layer height.
        </div>
      </details>

    </div>
  </div>
</body>
</html>
"""


# ===================== FLASK + CORE LOGIC =====================

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-secret")

GENERATED: Dict[str, Dict[str, object]] = {}
GENERATED_TTL_SECONDS = 20 * 60  # 20 minutes

DEFAULT_Z_MATCH_TOL = 0.05
DEFAULT_Z_FLOOR_TOL = 0.05


@app.before_request
def _log_req():
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or request.headers.get("X-Real-IP")
          or request.remote_addr)
    ua = request.headers.get("User-Agent", "")
    path = request.path
    ref = request.headers.get("Referer", "")
    print(f"REQ ip={ip} path={path} ua={ua} ref={ref}", flush=True)


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


def _detect_extrusion_mode_and_last_e(lines: List[str]) -> Tuple[str, float]:
    mode = "absolute"
    last_e = 0.0

    for raw in lines:
        code = _strip_comment(raw)
        if not code:
            continue
        up = code.upper()

        if up.startswith("M82"):
            mode = "absolute"
            continue
        if up.startswith("M83"):
            mode = "relative"
            continue

        if up.startswith("G92"):
            e = _extract_float_param(code, "E")
            if e is not None:
                last_e = float(e)
            continue

        if _is_motion(code) and mode == "absolute":
            e = _extract_float_param(code, "E")
            if e is not None:
                last_e = float(e)

    return mode, last_e


def _replace_e_value(line: str, new_e: float) -> str:
    if ";" in line:
        code_part, comment = line.split(";", 1)
        comment = ";" + comment
    else:
        code_part, comment = line, ""

    def repl(m: re.Match) -> str:
        return f"{m.group(1)}{new_e:.5f}"

    new_code = re.sub(r"(?i)(\bE\s*)(?:=\s*)?([-+]?\d*\.?\d+)", repl, code_part, count=1).rstrip()
    if comment:
        if not new_code.endswith(" "):
            new_code += " "
        new_code += comment.lstrip()
    return new_code


def _convert_segment_to_relative_e(segment_lines: List[str], last_e_abs: float) -> List[str]:
    out: List[str] = []
    cur = float(last_e_abs)

    for ln in segment_lines:
        if not ln.strip():
            out.append(ln)
            continue

        code = _strip_comment(ln)
        if not code:
            out.append(ln)
            continue

        up = code.upper()

        if up.startswith("G92"):
            e = _extract_float_param(code, "E")
            if e is not None:
                cur = float(e)
                out.append("G92 E0")
            else:
                out.append(ln)
            continue

        if _is_motion(code):
            e_abs = _extract_float_param(code, "E")
            if e_abs is None:
                out.append(ln)
                continue
            e_abs = float(e_abs)
            e_rel = e_abs - cur
            cur = e_abs
            out.append(_replace_e_value(ln, e_rel))
            continue

        out.append(ln)

    return out


def _find_anchor_and_context(
    gcode_lines: List[str],
    resume_z: float,
    *,
    z_match_tol: float,
) -> AnchorResult:
    current_z: Optional[float] = None
    last_motion_f: Optional[float] = None
    context: List[str] = []

    for i, raw in enumerate(gcode_lines):
        zc = _extract_z_comment(raw)
        if zc is not None:
            current_z = float(zc)

        if _is_motion(raw):
            z = _extract_float_param(raw, "Z")
            if z is not None:
                current_z = float(z)

            f = _extract_float_param(raw, "F")
            if f is not None:
                last_motion_f = float(f)

        if current_z is not None and current_z >= (resume_z - z_match_tol):
            if not should_strip_line(raw) and is_real_printing_move(raw):
                mode, last_e_abs = _detect_extrusion_mode_and_last_e(context)
                return AnchorResult(
                    anchor_index=i,
                    resume_z=resume_z,
                    detected_e_mode=mode,
                    last_e_abs=last_e_abs,
                    last_motion_f=last_motion_f,
                )

        context.append(raw)

    raise ValueError("Could not find a resume anchor at/after computed resume height.")


def build_resumed_gcode(
    original_gcode_text: str,
    *,
    firmware: str,
    layer_height_mm: float,
    print_height_mm: float,
    z_match_tol: float = DEFAULT_Z_MATCH_TOL,
    z_floor_tol: float = DEFAULT_Z_FLOOR_TOL,
    inject_last_motion_feedrate: bool = True,
    include_user_check_messages: bool = True,
) -> Tuple[str, float]:
    gcode_lines = original_gcode_text.splitlines()
    resume_z = infer_resume_z(print_height_mm=print_height_mm, layer_height_mm=layer_height_mm)

    anchor = _find_anchor_and_context(
        gcode_lines,
        resume_z=resume_z,
        z_match_tol=z_match_tol,
    )

    kept: List[str] = []
    z_floor = resume_z - float(z_floor_tol)

    for raw in gcode_lines[anchor.anchor_index:]:
        if should_strip_line(raw):
            continue

        if _is_motion(raw):
            z = _extract_float_param(raw, "Z")
            if z is not None and float(z) < z_floor:
                continue

        kept.append(raw)

    if not kept:
        raise ValueError("Internal error: nothing kept after anchor.")

    if anchor.detected_e_mode == "absolute":
        kept = _convert_segment_to_relative_e(kept, last_e_abs=anchor.last_e_abs)

    header: List[str] = []
    header.append("; --- RESUME FROM FAILURE (LAZARUS) ---")
    header.append(f"; Inputs: LH={layer_height_mm:.5f}mm, PH={print_height_mm:.3f}mm")
    header.append(f"; Computed resume height (RH): {resume_z:.3f} mm (nearest multiple of LH)")
    header.append(f"; Anchor index: {anchor.anchor_index}")
    header.append(f"; Z-match tol: {z_match_tol:.3f} mm | Z-floor guard: Z >= {z_floor:.3f} mm")
    header.append(f"; Detected extrusion mode in source: {anchor.detected_e_mode.upper()}")
    header.append("G90 ; absolute positioning")
    header.append("G21 ; millimeters")
    header.append("M83 ; relative extrusion (Lazarus-safe)")
    header.append("G92 E0 ; reset extruder")

    if inject_last_motion_feedrate and anchor.last_motion_f is not None:
        header.append(f"G1 F{anchor.last_motion_f:.3f} ; inherit slicer feedrate before anchor")

    header.append("; --- BEGIN RESUMED TOOLPATH ---")

    out_lines: List[str] = []
    out_lines.extend(header)
    out_lines.extend(kept)
    out_lines.append("; --- END RESUMED FILE ---")

    return "\n".join(out_lines) + "\n", resume_z


def _cleanup_generated() -> None:
    now = time.time()
    dead: List[str] = []
    for k, v in GENERATED.items():
        ts = float(v.get("ts", 0.0))
        if now - ts > GENERATED_TTL_SECONDS:
            dead.append(k)
    for k in dead:
        GENERATED.pop(k, None)


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

    try:
        original_text = file.read().decode("utf-8", errors="ignore")
    except Exception as e:
        flash(f"Could not read file: {e}")
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

    try:
        new_gcode, resume_z = build_resumed_gcode(
            original_gcode_text=original_text,
            firmware=form_state["firmware"],
            layer_height_mm=layer_h,
            print_height_mm=print_h,
            z_match_tol=z_match_tol,
            z_floor_tol=z_floor_tol,
            inject_last_motion_feedrate=bool(form_state["inject_f"]),
            include_user_check_messages=bool(form_state["user_msgs"]),
        )
    except Exception as e:
        flash(f"Error generating recovery G-code: {e}")
        return redirect(url_for("index"))

    token = secrets.token_urlsafe(16)
    base_name = os.path.splitext(file.filename or "resume")[0]
    out_name = f"{base_name}_LAZARUS_RH_{resume_z:.3f}.gcode"
    GENERATED[token] = {"bytes": new_gcode.encode("utf-8"), "name": out_name, "ts": time.time()}

    preview_lines = 220
    lines = new_gcode.splitlines()
    preview = "\n".join(lines[:preview_lines])

    return render_template_string(
        HTML_PAGE,
        preview=preview,
        token=token,
        preview_lines=preview_lines,
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

    buf = io.BytesIO()
    buf.write(rec["bytes"])
    buf.seek(0)

    return send_file(
        buf,
        mimetype="text/plain",
        as_attachment=True,
        download_name=str(rec["name"]),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)


