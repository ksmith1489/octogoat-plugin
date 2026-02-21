from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_Z_MATCH_TOL = 0.05
DEFAULT_Z_FLOOR_TOL = 0.05


@dataclass
class ResumeDatum:
    x: float
    y: float
    z: float


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


def build_resumed_gcode(
    original_gcode_text: str,
    *,
    firmware: str,
    layer_height_mm: float,
    print_height_mm: float,
    z_match_tol: float = DEFAULT_Z_MATCH_TOL,
    z_floor_tol: float = DEFAULT_Z_FLOOR_TOL,
    inject_last_motion_feedrate: bool = True,
    preview_lines: int = 220,
) -> Dict[str, Any]:
    """
    Pure engine: returns resumed_text + preview + metadata.
    Does NOT move printer, does NOT write files.
    """
    resume_z = infer_resume_z(print_height_mm=print_height_mm, layer_height_mm=layer_height_mm)
    z_floor = resume_z - float(z_floor_tol)

    detected_mode = "absolute"
    last_e_abs = 0.0
    last_motion_f: Optional[float] = None
    current_x: Optional[float] = None
    current_y: Optional[float] = None
    current_z: Optional[float] = None
    anchor_datum: Optional[ResumeDatum] = None
    anchor_index: Optional[int] = None

    # PASS 1: find anchor + last E + last F
    for i, raw in enumerate(io.StringIO(original_gcode_text)):
        zc = _extract_z_comment(raw)
        if zc is not None:
            current_z = float(zc)

        code = _strip_comment(raw)
        up = code.upper() if code else ""

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

        if _is_motion(raw):
            x = _extract_float_param(raw, "X")
            if x is not None:
                current_x = float(x)

            y = _extract_float_param(raw, "Y")
            if y is not None:
                current_y = float(y)

            z = _extract_float_param(raw, "Z")
            if z is not None:
                current_z = float(z)

            f = _extract_float_param(raw, "F")
            if f is not None:
                last_motion_f = float(f)

        if current_z is not None and current_z >= (resume_z - z_match_tol):
            if (not should_strip_line(raw)) and is_real_printing_move(raw):
                anchor_index = i
                anchor_datum = ResumeDatum(
                    x=float(current_x if current_x is not None else 0.0),
                    y=float(current_y if current_y is not None else 0.0),
                    z=float(current_z),
                )
                break

    if anchor_index is None:
        raise ValueError("Could not find a resume anchor at/after computed resume height.")

    header: List[str] = []
    header.append("; --- RESUME FROM FAILURE (OCTOGOAT) ---")
    header.append(f"; Inputs: LH={layer_height_mm:.5f}mm, PH={print_height_mm:.3f}mm")
    header.append(f"; Computed resume height (RH): {resume_z:.3f} mm (nearest multiple of LH)")
    header.append(f"; Anchor index: {anchor_index}")
    header.append(f"; Z-match tol: {z_match_tol:.3f} mm | Z-floor guard: Z >= {z_floor:.3f} mm")
    header.append(f"; Detected extrusion mode in source: {detected_mode.upper()}")
    header.append("G90 ; absolute positioning")
    header.append("G21 ; millimeters")
    header.append("M83 ; relative extrusion (OctoGoat-safe)")
    header.append("G92 E0 ; reset extruder")
    if inject_last_motion_feedrate and last_motion_f is not None:
        header.append(f"G1 F{last_motion_f:.3f} ; inherit slicer feedrate before anchor")
    header.append("; --- BEGIN RESUMED TOOLPATH ---")

    out_lines: List[str] = []
    preview_buf: List[str] = []

    def add(line: str) -> None:
        out_lines.append(line)
        if len(preview_buf) < preview_lines:
            preview_buf.append(line)

    for ln in header:
        add(ln)

    cur_abs_e = float(last_e_abs)

    # PASS 2: emit from anchor onward
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

        add(out_line)

    add("; --- END RESUMED FILE ---")

    return dict(
        ok=True,
        firmware=(firmware or "").lower(),
        resume_z=round(resume_z, 3),
        datum=dict(
            x=float(anchor_datum.x if anchor_datum else 0.0),
            y=float(anchor_datum.y if anchor_datum else 0.0),
            z=float(anchor_datum.z if anchor_datum else 0.0),
        ),
        preview=preview_buf,
        resumed_text="\n".join(out_lines) + "\n",
    )