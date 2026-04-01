from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


DEFAULT_Z_MATCH_TOL = 0.05
DEFAULT_Z_FLOOR_TOL = 0.05
LAYER_HEIGHT_PATTERNS = (
    re.compile(r"(?i)^\s*;\s*layer[_ ]height\s*[:=]\s*([-+]?\d*\.?\d+)\s*$"),
    re.compile(r"(?i)^\s*;\s*layerheight\s*[:=]\s*([-+]?\d*\.?\d+)\s*$"),
)
INITIAL_LAYER_HEIGHT_PATTERNS = (
    re.compile(r"(?i)^\s*;\s*initial[_ ]layer[_ ]height\s*[:=]\s*([-+]?\d*\.?\d+\s*%?)\s*$"),
    re.compile(r"(?i)^\s*;\s*first[_ ]layer[_ ]height\s*[:=]\s*([-+]?\d*\.?\d+\s*%?)\s*$"),
    re.compile(r"(?i)^\s*;\s*initial layer height\s*[:=]\s*([-+]?\d*\.?\d+\s*%?)\s*$"),
    re.compile(r"(?i)^\s*;\s*first layer height\s*[:=]\s*([-+]?\d*\.?\d+\s*%?)\s*$"),
)


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


def normalize_alignment_side(alignment_side: Optional[str], quadrant: Optional[str] = None) -> str:
    side = (alignment_side or "").strip().lower()
    if side in ("left", "l"):
        return "left"
    if side in ("right", "r"):
        return "right"

    quadrant_value = (quadrant or "").strip().lower()
    if quadrant_value in ("fl", "bl"):
        return "left"
    if quadrant_value in ("fr", "br"):
        return "right"

    return "left"


def infer_resume_z(print_height_mm: float, layer_height_mm: float) -> float:
    if layer_height_mm <= 0:
        raise ValueError("Layer height must be > 0.")
    if print_height_mm < 0:
        raise ValueError("Print height must be >= 0.")
    k = int(round(print_height_mm / layer_height_mm))
    return max(0.0, k * layer_height_mm)


def infer_layer_height(original_gcode_text: str) -> float:
    for raw in io.StringIO(original_gcode_text):
        stripped = raw.strip()
        for pattern in LAYER_HEIGHT_PATTERNS:
            match = pattern.match(stripped)
            if not match:
                continue
            try:
                value = float(match.group(1))
            except Exception:
                continue
            if value > 0:
                return value

    layer_z_values = _collect_layer_z_values(original_gcode_text, printing_only=True)
    if len(layer_z_values) < 2:
        layer_z_values = _collect_layer_z_values(original_gcode_text, printing_only=False)
    if len(layer_z_values) < 2:
        raise ValueError("Could not detect layer height from selected GCODE.")

    diffs = []
    for previous, current in zip(layer_z_values, layer_z_values[1:]):
        diff = round(current - previous, 5)
        if diff > 0:
            diffs.append(diff)

    if not diffs:
        raise ValueError("Could not detect layer height from selected GCODE.")

    counts = Counter(diffs)
    best_diff, _ = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return float(best_diff)


def _parse_height_value(raw_value: str, *, layer_height_mm: float) -> Optional[float]:
    value = (raw_value or "").strip()
    if not value:
        return None

    if value.endswith("%"):
        try:
            return layer_height_mm * (float(value[:-1].strip()) / 100.0)
        except Exception:
            return None

    try:
        return float(value)
    except Exception:
        return None


def infer_initial_layer_height(original_gcode_text: str, *, layer_height_mm: float) -> float:
    for raw in io.StringIO(original_gcode_text):
        stripped = raw.strip()
        for pattern in INITIAL_LAYER_HEIGHT_PATTERNS:
            match = pattern.match(stripped)
            if not match:
                continue
            parsed = _parse_height_value(match.group(1), layer_height_mm=layer_height_mm)
            if parsed is not None and parsed > 0:
                return float(parsed)

    layer_z_values = _collect_layer_z_values(original_gcode_text, printing_only=True)
    if not layer_z_values:
        layer_z_values = _collect_layer_z_values(original_gcode_text, printing_only=False)
    if layer_z_values:
        return float(layer_z_values[0])

    return float(layer_height_mm)


def infer_true_print_height(
    print_height_mm: float,
    *,
    layer_height_mm: float,
    initial_layer_height_mm: float,
) -> Dict[str, float]:
    layer_adjustment = float(initial_layer_height_mm) - float(layer_height_mm)
    normalized_height = max(0.0, float(print_height_mm) - layer_adjustment)
    rounded_normalized_height = infer_resume_z(
        print_height_mm=normalized_height,
        layer_height_mm=layer_height_mm,
    )
    true_print_height = max(0.0, rounded_normalized_height + layer_adjustment)

    return dict(
        layer_adjustment=round(layer_adjustment, 5),
        normalized_height=round(normalized_height, 5),
        rounded_normalized_height=round(rounded_normalized_height, 5),
        true_print_height=round(true_print_height, 5),
    )


def _collect_layer_z_values(original_gcode_text: str, *, printing_only: bool) -> List[float]:
    current_z: Optional[float] = None
    seen = set()
    ordered: List[float] = []

    for raw in io.StringIO(original_gcode_text):
        zc = _extract_z_comment(raw)
        if zc is not None:
            current_z = float(zc)

        if not _is_motion(raw):
            continue

        z = _extract_float_param(raw, "Z")
        if z is not None:
            current_z = float(z)

        if current_z is None or current_z <= 0:
            continue

        if printing_only and not is_real_printing_move(raw):
            continue

        rounded = round(current_z, 5)
        if rounded not in seen:
            seen.add(rounded)
            ordered.append(rounded)

    return ordered


def _collect_layer_points(
    original_gcode_text: str,
    *,
    target_z: float,
    z_match_tol: float,
) -> List[ResumeDatum]:
    points: List[ResumeDatum] = []
    current_x: Optional[float] = None
    current_y: Optional[float] = None
    current_z: Optional[float] = None

    for raw in io.StringIO(original_gcode_text):
        if should_strip_line(raw):
            continue

        zc = _extract_z_comment(raw)
        if zc is not None:
            current_z = float(zc)

        if not _is_motion(raw):
            continue

        x = _extract_float_param(raw, "X")
        if x is not None:
            current_x = float(x)

        y = _extract_float_param(raw, "Y")
        if y is not None:
            current_y = float(y)

        z = _extract_float_param(raw, "Z")
        if z is not None:
            current_z = float(z)

        if current_z is None or abs(current_z - target_z) > z_match_tol:
            continue
        if current_x is None or current_y is None:
            continue

        points.append(ResumeDatum(x=float(current_x), y=float(current_y), z=float(target_z)))

    return points


def choose_alignment_datum(points: List[ResumeDatum], alignment_side: str, resume_z: float) -> ResumeDatum:
    if not points:
        raise ValueError("Could not find motion points at the computed resume layer.")

    normalized_side = normalize_alignment_side(alignment_side)
    target_x = min(point.x for point in points)
    if normalized_side == "right":
        target_x = max(point.x for point in points)

    matching_points = [point for point in points if abs(point.x - target_x) <= 0.00001]
    chosen_point = min(matching_points, key=lambda point: (point.y, point.x))

    return ResumeDatum(x=float(target_x), y=float(chosen_point.y), z=float(resume_z))


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
    print_height_mm: float,
    alignment_side: str = "left",
    layer_height_mm: Optional[float] = None,
    quadrant: Optional[str] = None,
    z_match_tol: float = DEFAULT_Z_MATCH_TOL,
    z_floor_tol: float = DEFAULT_Z_FLOOR_TOL,
    inject_last_motion_feedrate: bool = True,
    preview_lines: int = 50,
) -> Dict[str, Any]:
    """
    Pure engine: returns resumed_text + preview + metadata.
    Does NOT move printer, does NOT write files.
    """
    normalized_side = normalize_alignment_side(alignment_side, quadrant=quadrant)
    resolved_layer_height = float(layer_height_mm) if layer_height_mm is not None else infer_layer_height(original_gcode_text)
    resolved_initial_layer_height = infer_initial_layer_height(
        original_gcode_text,
        layer_height_mm=resolved_layer_height,
    )
    height_info = infer_true_print_height(
        print_height_mm=print_height_mm,
        layer_height_mm=resolved_layer_height,
        initial_layer_height_mm=resolved_initial_layer_height,
    )
    resume_z = float(height_info["true_print_height"])
    z_floor = resume_z - float(z_floor_tol)

    layer_points = _collect_layer_points(
        original_gcode_text,
        target_z=resume_z,
        z_match_tol=z_match_tol,
    )
    datum = choose_alignment_datum(layer_points, normalized_side, resume_z)

    detected_mode = "absolute"
    last_e_abs = 0.0
    last_motion_f: Optional[float] = None
    current_x: Optional[float] = None
    current_y: Optional[float] = None
    current_z: Optional[float] = None
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
                break

    if anchor_index is None:
        raise ValueError("Could not find a resume anchor at/after computed resume height.")

    header: List[str] = []
    header.append("; --- RESUME FROM FAILURE (OCTOGOAT) ---")
    header.append(
        f"; Inputs: LH={resolved_layer_height:.5f}mm, ILH={resolved_initial_layer_height:.5f}mm, PH={print_height_mm:.3f}mm"
    )
    header.append(
        f"; Adjusted print height: {height_info['normalized_height']:.5f} mm | Layer delta: {height_info['layer_adjustment']:.5f} mm"
    )
    header.append(f"; Computed resume height (RH): {resume_z:.3f} mm")
    header.append(f"; Alignment side: {normalized_side}")
    header.append(f"; Datum: X{datum.x:.3f} Y{datum.y:.3f} Z{datum.z:.3f}")
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
        layer_height=round(resolved_layer_height, 5),
        initial_layer_height=round(resolved_initial_layer_height, 5),
        adjusted_print_height=round(height_info["normalized_height"], 5),
        alignment_side=normalized_side,
        resume_z=round(resume_z, 3),
        datum=dict(
            x=float(datum.x),
            y=float(datum.y),
            z=float(datum.z),
            alignment_side=normalized_side,
        ),
        preview=preview_buf,
        resumed_text="\n".join(out_lines) + "\n",
    )
