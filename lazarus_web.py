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
    request,
    jsonify,
    json,
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
          <label>Z match tolerance (mm)(advanced used only) (default {{ form.z_match_tol or '0.05' }}):
            <input type="number" step="0.01" name="z_match_tol" value="{{ form.z_match_tol or '0.05' }}">
          </label>
          <label>Z floor guard (mm) (advanced use only)(default {{ form.z_floor_tol or '0.05' }}):
            <input type="number" step="0.01" name="z_floor_tol" value="{{ form.z_floor_tol or '0.05' }}">
          </label>
        </div>

        <div class="row">
          <label>
            <input type="checkbox" name="inject_f" value="1" {% if form.inject_f %}checked{% endif %}>
            Inherit slicer feedrate near anchor (recommended)
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
        <summary style="cursor:pointer; color:#aaa; font-weight:bold;">Reorientation Instructions brand/firmware specific</summary>
        <div style="margin-top:10px; color:#ddd; line-height:1.45;">
          Copy and paste this into your prefered AI / LLM prompt box with your model and firmware, “My printer is a [PRINTER MODEL] running [FIRMWARE].It normally parks at X[ ] Y[ ] Z[ ] after a print stops. I want to re-establish the printer’s position without homing, so I can resume a failed print.Please give only the commands I should use, and briefly explain what each one does.” end prompt,
          (where the printhead is parked upon stopping or canceling a print which is what you do when you see one failing. This is where you want to know what the coordinates are for this spot while the printer is online and internal geometry nas not been lost,  Then when you stop it or whatever you know that if the toolhead is there the cooridinates are x_ y_ z_ (you will find this on your fluidd, mainsale, octoapp, UI),  You maybe able to home x and y safely unlock motion control and drop the nozzle to the bed safely and get true z=0 and it would be the same as if you had homed.  Usually the parking spot is good enough when you know the coordinates ahead of time and no exactly where that spot is exactly.  If you have access to your printer.cfg you can ask an Ai / LLM to write you custom macros so that coordinates are restored from the stop parking spot with one click or pick a corner of your print bed to keep clear and use that as a landing pad and have AI write you a custom Lazarus Homing Macro.  Use common sense and practice before you do a live one and keep your finger near the power off button till you know it is right then your resume process is like 2 minutes.
           
        </div>
      </details>

    </div>
  </div>
</body>
</html>
"""


# ===================== FLASK + CORE LOGIC =====================

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

LAZARUS_API_KEY = os.environ.get("LAZARUS_API_KEY")

def require_api_key():
    # Only protect API routes
    if not request.path.startswith("/api/"):
        return True

    # If no key is configured, fail closed but cleanly
    if not LAZARUS_API_KEY:
        return False

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False

    key = auth.split(" ", 1)[1].strip()
    return key == LAZARUS_API_KEY



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

def find_layer_extremes_at_z(gcode_lines, target_z, layer_height):
    """
    Scan G-code lines and locate the layer closest to target_z.
    Return a dict of XY extrema at that layer.

    Returns:
        {
            'front_left': (x, y),
            'front_right': (x, y),
            'back_left': (x, y),
            'back_right': (x, y)
        }

    Rules:
    - Ignore comment lines
    - Track absolute X, Y, Z positions
    - Assume absolute positioning (G90)
    - Determine a Z window of ±(layer_height / 2) around target_z
    - Collect all XY positions where Z falls inside that window
    - Compute min_x, max_x, min_y, max_y
    - If no positions are found, return None
    - Handle missing X or Y by carrying forward last known values
    """
    # Usage: pass a list/iterable of raw G-code lines plus target Z + layer height.
    try:
        z_half_window = abs(float(layer_height)) / 2.0
        z_min = float(target_z) - z_half_window
        z_max = float(target_z) + z_half_window
    except Exception:
        return None

    current_x: Optional[float] = None
    current_y: Optional[float] = None
    current_z: Optional[float] = None
    xy_points: List[Tuple[float, float]] = []

    for raw_line in gcode_lines or []:
        try:
            line = str(raw_line).strip()
        except Exception:
            continue

        if not line or line.startswith(";"):
            continue

        code = line.split(";", 1)[0].strip()
        if not code:
            continue

        next_x = _extract_float_param(code, "X")
        next_y = _extract_float_param(code, "Y")
        next_z = _extract_float_param(code, "Z")

        if next_x is not None:
            current_x = next_x
        if next_y is not None:
            current_y = next_y
        if next_z is not None:
            current_z = next_z

        if current_z is None or current_x is None or current_y is None:
            continue

        if z_min <= current_z <= z_max:
            xy_points.append((current_x, current_y))

    if not xy_points:
        return None

    min_x = min(pt[0] for pt in xy_points)
    max_x = max(pt[0] for pt in xy_points)
    min_y = min(pt[1] for pt in xy_points)
    max_y = max(pt[1] for pt in xy_points)

    return {
        "front_left": (min_x, min_y),
        "front_right": (max_x, min_y),
        "back_left": (min_x, max_y),
        "back_right": (max_x, max_y),
    }




def infer_resume_z(print_height_mm: float, layer_height_mm: float) -> float:
    if layer_height_mm <= 0:
        raise ValueError("Layer height must be > 0.")
    if print_height_mm < 0:
        raise ValueError("Print height must be >= 0.")
    k = int(round(print_height_mm / layer_height_mm))
    return max(0.0, k * layer_height_mm)



def compute_datum_point(gcode_lines, target_height_mm, layer_height_mm, quadrant):
    target_z = infer_resume_z(
        print_height_mm=float(target_height_mm),
        layer_height_mm=float(layer_height_mm),
    )

    corners = find_layer_extremes_at_z(gcode_lines, target_z, layer_height_mm)
    if corners is None:
        return None

    if quadrant not in {"front_left", "front_right", "back_left", "back_right"}:
        raise ValueError("quadrant must be one of: front_left, front_right, back_left, back_right")

    selected_corner = None
    if isinstance(corners, dict):
        selected_corner = corners.get(quadrant)
    elif isinstance(corners, (list, tuple)) and len(corners) == 4:
        index_map = {
            "front_left": 0,
            "front_right": 1,
            "back_left": 2,
            "back_right": 3,
        }
        selected_corner = corners[index_map[quadrant]]

    if selected_corner is None:
        return None

    datum_x, datum_y = selected_corner
    datum_z = target_z
    return (datum_x, datum_y, datum_z)


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

@app.route("/api/ping", methods=["GET"])
def api_ping():
    if not require_api_key():
        return jsonify({"error": "invalid or missing API key"}), 401

    return jsonify({
        "ok": True,
        "service": "lazarus",
        "engine": "alive"
    })

@app.route("/api/jobs", methods=["POST"])
def api_jobs():
    if not require_api_key():
        return Response(
            '{"error":"invalid or missing API key"}',
            status=401,
            mimetype="application/json",
        )

    file = request.files.get("gcode_file")
    if not file:
        return Response(
            '{"error":"missing gcode_file"}',
            status=400,
            mimetype="application/json",
        )

    try:
        layer_height = float(request.form.get("layer_height"))
        print_height = float(request.form.get("print_height"))
        firmware = (request.form.get("firmware") or "klipper").lower()

        original_text = file.read().decode("utf-8", errors="ignore")
        token = secrets.token_urlsafe(16)
        out_path = str(GEN_DIR / f"{token}.gcode")

        resume_z, preview = build_resumed_gcode_to_file(
            original_gcode_text=original_text,
            firmware=firmware,
            layer_height_mm=layer_height,
            print_height_mm=print_height,
            z_match_tol=DEFAULT_Z_MATCH_TOL,
            z_floor_tol=DEFAULT_Z_FLOOR_TOL,
            inject_last_motion_feedrate=True,
            include_user_check_messages=True,
            out_path=out_path,
            preview_lines=120,
        )

    except ValueError as e:
        return Response(
            json.dumps({
                "ok": False,
                "error": str(e)
            }),
            status=422,
            mimetype="application/json",
        )

    GENERATED[token] = {
        "path": out_path,
        "name": f"LAZARUS_RH_{resume_z:.3f}.gcode",
        "ts": time.time(),
    }

    return Response(
        json.dumps({
            "ok": True,
            "resume_z": round(resume_z, 3),
            "download_url": f"/download/{token}",
            "preview": preview.splitlines()[:40],
        }),
        mimetype="application/json",
    )


@app.route("/download/<token>")
def api_download(token):
    entry = GENERATED.get(token)
    if not entry:
        return Response("Not found", status=404)

    return send_file(
        entry["path"],
        as_attachment=True,
        download_name=entry["name"],
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)