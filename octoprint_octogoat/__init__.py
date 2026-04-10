# coding=utf-8
from __future__ import absolute_import

import os
import re
import time
import uuid

import flask
import octoprint.plugin
import requests

from .resume_engine import build_resumed_gcode


WEEK_SECONDS = 7 * 24 * 60 * 60
ASSUMED_POSITION_MARKER_START = "; --- OctoGOAT Assumed Position ---"
ASSUMED_POSITION_MARKER_END = "; --- End OctoGOAT Assumed Position ---"
LEGACY_MARKER_START = "; --- OctoGOAT Smart Park ---"
LEGACY_MARKER_END = "; --- End OctoGOAT Smart Park ---"
LOCAL_STORAGE = "local"
ASSUMED_POSITION_BLOCK_RE = re.compile(
    re.escape(ASSUMED_POSITION_MARKER_START)
    + r"(.*?)"
    + re.escape(ASSUMED_POSITION_MARKER_END),
    flags=re.S,
)
ASSUMED_POSITION_MOVE_RE = re.compile(
    r"^\s*G(?:0|1)\d?\b[^\n;]*\bX\s*(?P<x>[+-]?(?:\d+(?:\.\d+)?|\.\d+))"
    + r"[^\n;]*\bY\s*(?P<y>[+-]?(?:\d+(?:\.\d+)?|\.\d+))"
    + r"[^\n;]*\bZ\s*(?P<z>[+-]?(?:\d+(?:\.\d+)?|\.\d+))",
    flags=re.I | re.M,
)


class OctoGoatPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.StartupPlugin,
):

    def get_settings_defaults(self):
        return dict(
            api_key="",
            install_id=str(uuid.uuid4()),
            last_validated=0,
            engine_url="https://app.lazarus3dprint.com",
            firmware_type="klipper",
            smart_park_enabled=False,
            smart_park_acknowledged=False,
            park_x=20.0,
            park_y=20.0,
            park_z="",
            park_z_offset=50.0,
            safe_z_hop=10.0,
        )

    def get_settings_restricted_paths(self):
        return dict(admin=[["api_key"]])

    def is_api_protected(self):
        return True

    def get_template_configs(self):
        return [
            dict(
                type="tab",
                name="OctoGoat",
                template="octogoat_tab.jinja2",
                custom_bindings=True,
            ),
            dict(
                type="settings",
                name="OctoGoat",
                template="octogoat_settings.jinja2",
                custom_bindings=False,
            ),
        ]

    def get_assets(self):
        return dict(
            js=["js/octogoat.js"],
            css=["css/octogoat.css"],
        )

    def get_api_commands(self):
        return dict(
            ping=[],
            status=[],
            validate=[],
            build_resume=["measured_height"],
            apply_park=[],
            set_assumed_position=["x", "y", "z"],
            goto_datum=["x", "y", "z"],
            lock_datum=["x", "y", "z"],
            execute_resume=[],
        )

    def on_after_startup(self):
        try:
            self._ensure_assumed_position_defaults()
            self.sync_assumed_position_scripts()
        except Exception as e:
            self._logger.error("Assumed position script sync failed: %s" % e)

        self._logger.info("OctoGOAT loaded successfully")
        self._logger.info("OctoGOAT plugin active")

    def on_api_get(self, request):
        if request.args.get("download_resume") != "1":
            return flask.jsonify(ok=True)

        if not hasattr(self, "_resume_cache"):
            response = flask.jsonify(ok=False, error="No resume built")
            response.status_code = 404
            return response

        filename = getattr(self, "_resume_filename", "octogoat_resume.gcode")
        response = flask.make_response(self._resume_cache)
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Content-Disposition"] = 'attachment; filename="{filename}"'.format(
            filename=filename
        )
        return response

    def on_api_command(self, command, data):
        data = data or {}

        try:
            return self._handle_api_command(command, data)
        except Exception as e:
            self._logger.exception("OctoGOAT API command failed: %s", command)
            return dict(ok=False, error=str(e))

    def _handle_api_command(self, command, data):
        if command == "ping":
            return dict(ok=True)

        if command == "status":
            return dict(
                ok=True,
                park=self._get_assumed_position(),
                current_file=self._get_current_job_file(),
            )

        if command == "validate":
            install_id = self._settings.get(["install_id"])
            last_validated = int(self._settings.get(["last_validated"]) or 0)
            engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
            validate_url = f"{engine_url}/validate"
            now = int(time.time())

            if last_validated and (now - last_validated) < WEEK_SECONDS:
                return dict(valid=True)

            try:
                response = requests.post(
                    validate_url,
                    json={"install_id": install_id},
                    timeout=5,
                )

                if response.status_code != 200:
                    return dict(valid=False)

                payload = response.json()
                is_valid = payload.get("valid") is True

                if is_valid:
                    self._settings.set(["last_validated"], now)
                    self._settings.save()

                return dict(valid=is_valid)
            except Exception:
                if last_validated and (now - last_validated) < WEEK_SECONDS:
                    return dict(valid=True)
                return dict(valid=False)

        if command == "build_resume":
            try:
                measured_height = float(data.get("measured_height"))
            except Exception:
                return dict(ok=False, error="Invalid measured height")

            legacy_layer_height = data.get("layer_height")
            if legacy_layer_height in ("", None):
                legacy_layer_height = None
            elif legacy_layer_height is not None:
                try:
                    legacy_layer_height = float(legacy_layer_height)
                except Exception:
                    return dict(ok=False, error="Invalid layer height")

            gcode_text, source = self._resolve_gcode_source(data)
            result = build_resumed_gcode(
                original_gcode_text=gcode_text,
                firmware=self._settings.get(["firmware_type"]),
                print_height_mm=measured_height,
                alignment_side=data.get("alignment_side") or data.get("side"),
                quadrant=data.get("quadrant"),
                layer_height_mm=legacy_layer_height,
            )

            self._resume_cache = result["resumed_text"]
            self._resume_source = source
            self._resume_filename = self._build_resume_filename(source)

            return dict(
                ok=True,
                layer_height=result["layer_height"],
                initial_layer_height=result["initial_layer_height"],
                adjusted_print_height=result["adjusted_print_height"],
                resume_z=result["resume_z"],
                alignment_side=result["alignment_side"],
                datum=result["datum"],
                preview=result["preview"],
                park=self._get_assumed_position(),
                file=source,
                resume_file_name=self._resume_filename,
            )

        if command == "apply_park":
            firmware = self._settings.get(["firmware_type"])
            park = self._get_assumed_position()

            if firmware == "klipper":
                cmd = "SET_KINEMATIC_POSITION X={x} Y={y} Z={z}".format(
                    x=self._format_gcode_value(park["x"]),
                    y=self._format_gcode_value(park["y"]),
                    z=self._format_gcode_value(park["z"]),
                )
            else:
                cmd = "G92 X{x} Y{y} Z{z}".format(
                    x=self._format_gcode_value(park["x"]),
                    y=self._format_gcode_value(park["y"]),
                    z=self._format_gcode_value(park["z"]),
                )

            self._printer.commands(cmd)
            return dict(ok=True, park=park)

        if command == "set_assumed_position":
            try:
                x = float(data.get("x"))
                y = float(data.get("y"))
                z = float(data.get("z"))
            except Exception:
                return dict(ok=False, error="Invalid assumed position")

            self._set_assumed_position(x=x, y=y, z=z)
            park = self._get_assumed_position_from_settings()
            self.sync_assumed_position_scripts(park=park)
            return dict(ok=True, park=park)

        if command == "goto_datum":
            x = float(data.get("x"))
            y = float(data.get("y"))
            z = float(data.get("z"))
            safe_hop = float(self._settings.get(["safe_z_hop"]) or 10.0)

            self._printer.commands(
                [
                    "G90",
                    "G0 Z{z}".format(z=self._format_gcode_value(z + safe_hop)),
                    "G0 X{x} Y{y}".format(
                        x=self._format_gcode_value(x),
                        y=self._format_gcode_value(y),
                    ),
                ]
            )
            return dict(ok=True)

        if command == "lock_datum":
            firmware = self._settings.get(["firmware_type"])
            x = float(data.get("x"))
            y = float(data.get("y"))
            z = float(data.get("z"))
            safe_hop = float(self._settings.get(["safe_z_hop"]) or 10.0)

            if firmware == "klipper":
                position_cmd = "SET_KINEMATIC_POSITION X={x} Y={y} Z={z}".format(
                    x=self._format_gcode_value(x),
                    y=self._format_gcode_value(y),
                    z=self._format_gcode_value(z),
                )
            else:
                position_cmd = "G92 X{x} Y{y} Z{z}".format(
                    x=self._format_gcode_value(x),
                    y=self._format_gcode_value(y),
                    z=self._format_gcode_value(z),
                )

            self._printer.commands(
                [
                    position_cmd,
                    "G91",
                    "G0 Z{z}".format(z=self._format_gcode_value(safe_hop)),
                    "G90",
                ]
            )
            return dict(ok=True, message="it is now safe to set nozzle temp")

        if command == "execute_resume":
            if not hasattr(self, "_resume_cache"):
                return dict(ok=False, error="No resume built")

            self._printer.commands("M400")
            self._printer.commands(self._resume_cache.splitlines())
            return dict(ok=True)

        return None

    def _get_current_job_file(self):
        printer = getattr(self, "_printer", None)
        if printer is None:
            return None

        try:
            current = printer.get_current_data() or {}
        except Exception:
            return None

        job = current.get("job") or {}
        file_info = job.get("file") or {}
        name = file_info.get("name")
        path = file_info.get("path")
        origin = file_info.get("origin")

        if not name and not path:
            return None

        return dict(
            name=name or (os.path.basename(path) if path else None),
            path=path,
            origin=origin,
            supported=(origin == LOCAL_STORAGE and bool(path)),
        )

    def _resolve_gcode_source(self, data):
        uploaded_gcode_text = data.get("uploaded_gcode_text")
        uploaded_file_name = data.get("uploaded_file_name") or "uploaded.gcode"
        if isinstance(uploaded_gcode_text, str) and uploaded_gcode_text.strip():
            return uploaded_gcode_text, dict(
                source="device",
                name=uploaded_file_name,
                path=None,
            )

        file_path = data.get("file_path")
        if file_path:
            return self._read_local_storage_file(file_path), dict(
                source="octoprint",
                name=os.path.basename(file_path),
                path=file_path,
            )

        current_file = self._get_current_job_file()
        if not current_file:
            raise ValueError("error, no file selected")
        if current_file.get("origin") != LOCAL_STORAGE:
            raise ValueError("Selected file must be stored in OctoPrint local storage or chosen from your device.")
        if not current_file.get("path"):
            raise ValueError("error, no file selected")

        return self._read_local_storage_file(current_file["path"]), dict(
            source="octoprint",
            name=current_file.get("name"),
            path=current_file.get("path"),
        )

    def _read_local_storage_file(self, file_path):
        try:
            absolute_path = self._file_manager.path_on_disk(LOCAL_STORAGE, file_path)
            with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except Exception as e:
            raise ValueError("File read failed: %s" % e)

    def _build_resume_filename(self, source):
        source_name = (source or {}).get("name") or "octogoat_resume"
        stem, _extension = os.path.splitext(source_name)
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
        if not cleaned:
            cleaned = "octogoat_resume"
        return cleaned + "_resume.gcode"

    def _get_printer_zmax(self):
        try:
            profile_manager = getattr(self, "_printer_profile_manager", None)
            if profile_manager is None:
                return None

            profile = profile_manager.get_current() or {}
            volume = profile.get("volume") or {}
            zmax = float(volume.get("height") or 0.0)
            if zmax > 0:
                return zmax
        except Exception:
            pass

        return None

    def _get_default_assumed_position_z(self):
        zmax = self._get_printer_zmax()
        if zmax is not None:
            park_z = zmax - 50.0
            if park_z > 0:
                return park_z

        return 200.0

    def _ensure_assumed_position_defaults(self):
        stored_park_z = self._settings.get(["park_z"])

        if stored_park_z not in ("", None):
            return

        park_z = self._get_default_assumed_position_z()
        self._settings.set(["park_z"], park_z)
        self._settings.save()

    def _get_assumed_position_from_settings(self):
        park_x = float(self._settings.get(["park_x"]) or 20.0)
        park_y = float(self._settings.get(["park_y"]) or 20.0)
        zmax = self._get_printer_zmax()
        stored_park_z = self._settings.get(["park_z"])

        if stored_park_z in ("", None):
            park_z = self._get_default_assumed_position_z()
        else:
            park_z = float(stored_park_z)
            if zmax is not None:
                park_z = max(0.0, min(zmax, park_z))
            else:
                park_z = max(0.0, park_z)

        return dict(
            x=round(park_x, 3),
            y=round(park_y, 3),
            z=round(park_z, 3),
        )

    def _parse_assumed_position_from_script(self, script_text):
        if not isinstance(script_text, str) or not script_text.strip():
            return None

        block_match = ASSUMED_POSITION_BLOCK_RE.search(script_text)
        search_text = block_match.group(1) if block_match else script_text
        move_match = ASSUMED_POSITION_MOVE_RE.search(search_text)
        if not move_match:
            return None

        return dict(
            x=round(float(move_match.group("x")), 3),
            y=round(float(move_match.group("y")), 3),
            z=round(float(move_match.group("z")), 3),
        )

    def _assumed_positions_match(self, first, second):
        if not first or not second:
            return False

        return (
            round(float(first.get("x", 0.0)), 3) == round(float(second.get("x", 0.0)), 3)
            and round(float(first.get("y", 0.0)), 3) == round(float(second.get("y", 0.0)), 3)
            and round(float(first.get("z", 0.0)), 3) == round(float(second.get("z", 0.0)), 3)
        )

    def _get_assumed_position_from_scripts(self, settings_park=None):
        if settings_park is None:
            settings_park = self._get_assumed_position_from_settings()

        done_park = self._parse_assumed_position_from_script(
            self._settings.global_get(["scripts", "gcode", "afterPrintDone"]) or ""
        )
        cancelled_park = self._parse_assumed_position_from_script(
            self._settings.global_get(["scripts", "gcode", "afterPrintCancelled"]) or ""
        )

        if done_park and cancelled_park:
            if self._assumed_positions_match(done_park, cancelled_park):
                return cancelled_park
            if self._assumed_positions_match(done_park, settings_park):
                return cancelled_park
            if self._assumed_positions_match(cancelled_park, settings_park):
                return done_park
            return cancelled_park

        return cancelled_park or done_park

    def _sync_assumed_position_settings_from_scripts(self):
        settings_park = self._get_assumed_position_from_settings()
        script_park = self._get_assumed_position_from_scripts(settings_park=settings_park)

        if not script_park:
            return settings_park

        if not self._assumed_positions_match(script_park, settings_park):
            self._set_assumed_position(
                x=script_park["x"],
                y=script_park["y"],
                z=script_park["z"],
            )

        return script_park

    def _get_assumed_position(self):
        return self._sync_assumed_position_settings_from_scripts()

    def _set_assumed_position(self, *, x, y, z):
        zmax = self._get_printer_zmax()
        clamped_z = max(0.0, float(z))
        if zmax is not None:
            clamped_z = min(zmax, clamped_z)

        self._settings.set(["park_x"], float(x))
        self._settings.set(["park_y"], float(y))
        self._settings.set(["park_z"], clamped_z)
        if zmax is not None:
            self._settings.set(["park_z_offset"], max(0.0, zmax - clamped_z))
        self._settings.save()

    def _build_assumed_position_script(self, park=None):
        park = park or self._get_assumed_position_from_settings()
        return "\n".join(
            [
                ASSUMED_POSITION_MARKER_START,
                "G91",
                "G0 Z10",
                "G90",
                "G0 X{x} Y{y} Z{z}".format(
                    x=self._format_gcode_value(park["x"]),
                    y=self._format_gcode_value(park["y"]),
                    z=self._format_gcode_value(park["z"]),
                ),
                ASSUMED_POSITION_MARKER_END,
            ]
        )

    def _build_cancelled_shutdown_script(self, park=None):
        return "\n".join(
            [
                self._build_assumed_position_script(park=park),
                "",
                "M84",
                "M104 T0 S0",
                "M140 S0",
                "M106 S0",
            ]
        )

    def _merge_script_block(self, current_script, script_block, *, prepend=False):
        merged = current_script or ""

        for start_marker, end_marker in (
            (ASSUMED_POSITION_MARKER_START, ASSUMED_POSITION_MARKER_END),
            (LEGACY_MARKER_START, LEGACY_MARKER_END),
        ):
            pattern = re.compile(
                re.escape(start_marker) + r".*?" + re.escape(end_marker) + r"\s*",
                flags=re.S,
            )
            merged = pattern.sub("", merged)

        merged = merged.strip()
        if prepend:
            if merged:
                return script_block + "\n\n" + merged + "\n"
            return script_block + "\n"

        if merged:
            return merged + "\n\n" + script_block + "\n"
        return script_block + "\n"

    def sync_assumed_position_scripts(self, park=None):
        park = park or self._sync_assumed_position_settings_from_scripts()
        script_block = self._build_assumed_position_script(park=park)
        done_script = self._settings.global_get(["scripts", "gcode", "afterPrintDone"]) or ""

        self._settings.global_set(
            ["scripts", "gcode", "afterPrintDone"],
            self._merge_script_block(done_script, script_block),
        )
        self._settings.global_set(
            ["scripts", "gcode", "afterPrintCancelled"],
            self._build_cancelled_shutdown_script(park=park) + "\n",
        )

        self._settings.global_save()
        self._settings.set(["smart_park_enabled"], True)
        self._settings.save()

    def _format_gcode_value(self, value):
        formatted = "{:.3f}".format(float(value))
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        return formatted


__plugin_name__ = "OctoGOAT"
__plugin_version__ = "0.1.0"
__plugin_pythoncompat__ = ">=3.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = OctoGoatPlugin()
