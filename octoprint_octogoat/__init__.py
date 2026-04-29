# coding=utf-8
from __future__ import absolute_import

import os
import re
import time
import uuid
import io
from urllib.parse import urlparse, urlunparse

import flask
import octoprint.plugin
import requests

from .resume_engine import build_resumed_gcode


MONTH_SECONDS = 30 * 24 * 60 * 60
ASSUMED_POSITION_MARKER_START = "; --- OctoGOAT Assumed Position ---"
ASSUMED_POSITION_MARKER_END = "; --- End OctoGOAT Assumed Position ---"
LEGACY_MARKER_START = "; --- OctoGOAT Smart Park ---"
LEGACY_MARKER_END = "; --- End OctoGOAT Smart Park ---"
LOCAL_STORAGE = "local"
PLUGIN_CANCEL_SHUTDOWN_COMMANDS = (
    "M84",
    "M104 T0 S0",
    "M140 S0",
    "M106 S0",
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
            control_mode="octoprint",
            moonraker_url="",
            moonraker_api_key="",
            moonraker_park_x=20.0,
            moonraker_park_y=20.0,
            moonraker_park_z=200.0,
            moonraker_upload_and_print=False,
            moonraker_timeout_seconds=8,
            z_max_override_mm="",
        )

    def get_settings_restricted_paths(self):
        return dict(admin=[["api_key"], ["moonraker_api_key"]])

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
            set_control_mode=["control_mode"],
            test_moonraker=[],
            build_resume=["measured_height"],
            safe_resume_homing=[],
            apply_assumed_position=[],
            apply_park=[],
            set_assumed_position=["x", "y", "z"],
            goto_datum=["x", "y"],
            reset_alignment_z=[],
            lock_datum=["x", "y", "z"],
            execute_resume=[],
            upload_resume_to_moonraker=[],
        )

    def on_after_startup(self):
        try:
            self._ensure_assumed_position_defaults()
            self.cleanup_assumed_position_scripts()
        except Exception as e:
            self._logger.error("Assumed position startup cleanup failed: %s" % e)

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
                control_mode=self._get_control_mode(),
                moonraker_mode=self._is_moonraker_mode(),
                park=self._get_control_park_position(),
                current_file=self._get_current_job_file(),
            )

        if command == "set_control_mode":
            mode = str(data.get("control_mode") or "octoprint").strip().lower()
            if mode not in ("octoprint", "moonraker"):
                return dict(ok=False, error="Invalid control mode")

            self._settings.set(["control_mode"], mode)
            self._settings.save()
            return dict(
                ok=True,
                control_mode=mode,
                moonraker_mode=(mode == "moonraker"),
                park=self._get_control_park_position(),
            )

        if command == "test_moonraker":
            info = self._moonraker_server_info()
            klippy_connected = info.get("klippy_connected") is True
            klippy_state = info.get("klippy_state") or "unknown"
            if not klippy_connected:
                return dict(
                    ok=False,
                    klippy_connected=False,
                    klippy_state=klippy_state,
                    error="Moonraker is reachable, but Klippy is not connected (state: {state}).".format(
                        state=klippy_state
                    ),
                )

            return dict(
                ok=True,
                klippy_connected=True,
                klippy_state=klippy_state,
                message="Moonraker connected. Klippy state: {state}".format(state=klippy_state),
            )

        if command == "validate":
            install_id = self._settings.get(["install_id"])
            last_validated = int(self._settings.get(["last_validated"]) or 0)
            engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
            validate_url = f"{engine_url}/validate"
            now = int(time.time())

            if last_validated and (now - last_validated) < MONTH_SECONDS:
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
                if last_validated and (now - last_validated) < MONTH_SECONDS:
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
            self._last_measured_height = measured_height

            return dict(
                ok=True,
                layer_height=result["layer_height"],
                initial_layer_height=result["initial_layer_height"],
                adjusted_print_height=result["adjusted_print_height"],
                resume_z=result["resume_z"],
                alignment_side=result["alignment_side"],
                datum=result["datum"],
                preview=result["preview"],
                park=self._get_control_park_position(),
                file=source,
                resume_file_name=self._resume_filename,
            )

        if command == "safe_resume_homing":
            try:
                measured_height = float(data.get("measured_height"))
            except Exception:
                measured_height = getattr(self, "_last_measured_height", None)

            safe_z_info = self._resolve_safe_resume_z(measured_height=measured_height)
            safe_z = safe_z_info["z"]

            if self._uses_klipper_commands():
                commands = [
                    "SET_KINEMATIC_POSITION Z={z} SET_HOMED=Z".format(
                        z=self._format_gcode_value(safe_z)
                    ),
                    "G28 X Y",
                ]
            else:
                commands = [
                    "G92 Z{z}".format(z=self._format_gcode_value(safe_z)),
                    "G28 X Y",
                ]

            self._send_gcode_commands(commands)
            return dict(
                ok=True,
                safe_z=round(safe_z, 3),
                safe_z_source=safe_z_info["source"],
                message="Safe Resume Homing started. Z was set to {z} from {source}, then X/Y homing was requested.".format(
                    z=self._format_gcode_value(safe_z),
                    source=safe_z_info["source"],
                ),
            )

        if command in ("apply_park", "apply_assumed_position"):
            if self._is_moonraker_mode():
                park = self._get_moonraker_park_position()
                cmd = "SET_KINEMATIC_POSITION X={x} Y={y} Z={z}".format(
                    x=self._format_gcode_value(park["x"]),
                    y=self._format_gcode_value(park["y"]),
                    z=self._format_gcode_value(park["z"]),
                )
                self._moonraker_gcode(cmd)
                return dict(ok=True, park=park, message="Assumed position coordinates applied.")

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
            return dict(ok=True, park=park, message="Assumed position coordinates applied.")

        if command == "set_assumed_position":
            try:
                x = float(data.get("x"))
                y = float(data.get("y"))
                z = float(data.get("z"))
            except Exception:
                return dict(ok=False, error="Invalid assumed position")

            self._set_assumed_position(x=x, y=y, z=z)
            park = self._get_assumed_position_from_settings()
            return dict(ok=True, park=park)

        if command == "goto_datum":
            x = float(data.get("x"))
            y = float(data.get("y"))
            commands = [
                "G90",
                "G0 X{x} Y{y}".format(
                    x=self._format_gcode_value(x),
                    y=self._format_gcode_value(y),
                ),
            ]

            self._send_gcode_commands(commands)
            return dict(ok=True)

        if command == "reset_alignment_z":
            if self._uses_klipper_commands():
                commands = ["SET_KINEMATIC_POSITION Z=200 SET_HOMED=Z"]
            else:
                commands = ["G92 Z200"]

            self._send_gcode_commands(commands)
            return dict(ok=True, message="Z coordinate reset to 200 mm.")

        if command == "lock_datum":
            firmware = self._settings.get(["firmware_type"])
            x = float(data.get("x"))
            y = float(data.get("y"))
            z = float(data.get("z"))
            safe_hop = float(self._settings.get(["safe_z_hop"]) or 10.0)

            if self._is_moonraker_mode() or firmware == "klipper":
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

            commands = [
                position_cmd,
                "G91",
                "G0 Z{z}".format(z=self._format_gcode_value(safe_hop)),
                "G90",
            ]
            if self._is_moonraker_mode():
                self._moonraker_gcode("\n".join(commands))
            else:
                self._printer.commands(commands)
            return dict(ok=True, message="it is now safe to set nozzle temp")

        if command == "execute_resume":
            if not hasattr(self, "_resume_cache"):
                return dict(ok=False, error="No resume built")

            if self._is_moonraker_mode():
                return self._moonraker_upload_resume()

            self._printer.commands("M400")
            self._printer.commands(self._resume_cache.splitlines())
            return dict(ok=True)

        if command == "upload_resume_to_moonraker":
            if not hasattr(self, "_resume_cache"):
                return dict(ok=False, error="No resume built")

            return self._moonraker_upload_resume()

        return None

    def _get_control_mode(self):
        mode = str(self._settings.get(["control_mode"]) or "octoprint").strip().lower()
        if mode == "moonraker":
            return "moonraker"
        return "octoprint"

    def _is_moonraker_mode(self):
        return self._get_control_mode() == "moonraker"

    def _uses_klipper_commands(self):
        firmware = str(self._settings.get(["firmware_type"]) or "").strip().lower()
        return self._is_moonraker_mode() or firmware == "klipper"

    def _send_gcode_commands(self, commands):
        if self._is_moonraker_mode():
            self._moonraker_gcode("\n".join(commands))
            return

        self._printer.commands(commands)

    def _get_float_setting(self, path, default):
        try:
            return float(self._settings.get(path))
        except Exception:
            return float(default)

    def _get_bool_setting(self, path, default=False):
        value = self._settings.get(path)
        if value in ("true", "True", "1", 1, True):
            return True
        if value in ("false", "False", "0", 0, False):
            return False
        return bool(default)

    def _get_moonraker_park_position(self):
        return dict(
            x=round(self._get_float_setting(["moonraker_park_x"], 20.0), 3),
            y=round(self._get_float_setting(["moonraker_park_y"], 20.0), 3),
            z=round(self._get_float_setting(["moonraker_park_z"], 200.0), 3),
        )

    def _get_control_park_position(self):
        if self._is_moonraker_mode():
            return self._get_moonraker_park_position()
        return self._get_assumed_position()

    def _get_moonraker_timeout(self):
        return max(1.0, self._get_float_setting(["moonraker_timeout_seconds"], 8.0))

    def _get_z_max_override(self):
        value = self._settings.get(["z_max_override_mm"])
        if value in ("", None):
            return None

        try:
            zmax = float(value)
        except Exception:
            return None

        if zmax > 0:
            return zmax
        return None

    def _get_moonraker_base_url(self):
        base_url = str(self._settings.get(["moonraker_url"]) or "").strip()
        if not base_url:
            raise ValueError("Moonraker URL missing. Add it in OctoGoat settings.")

        if "://" not in base_url:
            base_url = "http://" + base_url

        parsed = urlparse(base_url)
        normalized_path = parsed.path or ""
        try:
            parsed_port = parsed.port
        except ValueError:
            raise ValueError("Moonraker URL has an invalid port. Check the URL in OctoGoat settings.")

        if parsed_port is None and normalized_path in ("", "/"):
            hostname = parsed.hostname or ""
            if ":" in hostname and not hostname.startswith("["):
                hostname = "[{hostname}]".format(hostname=hostname)

            auth = ""
            if parsed.username:
                auth = parsed.username
                if parsed.password:
                    auth += ":" + parsed.password
                auth += "@"

            parsed = parsed._replace(netloc="{auth}{hostname}:7125".format(
                auth=auth,
                hostname=hostname,
            ))

        return urlunparse(parsed).rstrip("/")

    def _get_moonraker_headers(self):
        headers = {}
        api_key = str(self._settings.get(["moonraker_api_key"]) or "").strip()
        if api_key:
            headers["X-Api-Key"] = api_key
        return headers

    def _extract_moonraker_error(self, response, payload):
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return error.get("message") or str(error)
            if error:
                return str(error)
            if payload.get("message"):
                return str(payload.get("message"))

        return response.text or "Moonraker request failed"

    def _moonraker_result(self, payload):
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload

    def _moonraker_request(self, method, path, **kwargs):
        base_url = self._get_moonraker_base_url()
        url = base_url + path
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._get_moonraker_headers())
        timeout = self._get_moonraker_timeout()

        self._logger.debug("Moonraker request: %s %s", method.upper(), path)

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=timeout,
                **kwargs
            )
        except requests.exceptions.Timeout:
            raise ValueError("Moonraker request timed out. Check the URL and network.")
        except requests.exceptions.ConnectionError:
            raise ValueError("Moonraker unreachable. Check the URL and network.")
        except requests.exceptions.RequestException as e:
            raise ValueError("Moonraker request failed: {error}".format(error=e))

        payload = None
        if response.content:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text

        self._logger.debug("Moonraker response: %s %s", response.status_code, path)

        if response.status_code in (401, 403):
            raise ValueError("Moonraker authentication failed. Check the API key in OctoGoat settings.")
        if response.status_code >= 400:
            raise ValueError(self._extract_moonraker_error(response, payload))

        return self._moonraker_result(payload)

    def _moonraker_server_info(self):
        result = self._moonraker_request("GET", "/server/info")
        if not isinstance(result, dict):
            raise ValueError("Moonraker returned an unexpected /server/info response.")
        return result

    def _moonraker_toolhead_zmax(self):
        try:
            result = self._moonraker_request("GET", "/printer/objects/query?toolhead")
        except Exception:
            return None

        if not isinstance(result, dict):
            return None

        status = result.get("status") or {}
        toolhead = status.get("toolhead") or {}
        axis_maximum = toolhead.get("axis_maximum")
        zmax = None

        if isinstance(axis_maximum, dict):
            zmax = axis_maximum.get("z") or axis_maximum.get("Z")
        elif isinstance(axis_maximum, (list, tuple)) and len(axis_maximum) >= 3:
            zmax = axis_maximum[2]

        try:
            zmax = float(zmax)
        except Exception:
            return None

        if zmax > 0:
            return zmax
        return None

    def _moonraker_require_klippy_connected(self):
        info = self._moonraker_server_info()
        if info.get("klippy_connected") is not True:
            state = info.get("klippy_state") or "unknown"
            raise ValueError(
                "Moonraker is reachable, but Klippy is not connected (state: {state}).".format(
                    state=state
                )
            )

        return info

    def _moonraker_gcode(self, script):
        self._moonraker_require_klippy_connected()

        try:
            return self._moonraker_request(
                "POST",
                "/printer/gcode/script",
                json={"script": script},
            )
        except ValueError as e:
            message = str(e)
            if "SET_KINEMATIC_POSITION" in script and "force_move" not in message.lower():
                message += (
                    " If Klipper rejects SET_KINEMATIC_POSITION, enable force_move "
                    "in your printer UI/settings, or add [force_move] "
                    "enable_force_move: True to printer.cfg and restart Klipper."
                )
            raise ValueError(message)

    def _moonraker_upload_resume(self):
        resume_text = getattr(self, "_resume_cache", None)
        if not resume_text:
            return dict(ok=False, error="No resume built")

        filename = getattr(self, "_resume_filename", "octogoat_resume.gcode")
        upload_and_print = self._get_bool_setting(["moonraker_upload_and_print"], False)
        if upload_and_print:
            self._moonraker_require_klippy_connected()

        data = {
            "root": "gcodes",
        }
        if upload_and_print:
            data["print"] = "true"

        files = {
            "file": (
                filename,
                io.BytesIO(resume_text.encode("utf-8")),
                "application/octet-stream",
            )
        }

        result = self._moonraker_request(
            "POST",
            "/server/files/upload",
            data=data,
            files=files,
        )
        item = result.get("item") if isinstance(result, dict) else {}
        uploaded_filename = (item or {}).get("path") or filename
        action = "uploaded and print requested" if upload_and_print else "uploaded"
        return dict(
            ok=True,
            filename=uploaded_filename,
            moonraker_result=result,
            message="Resume GCODE {action}: {filename}".format(
                action=action,
                filename=uploaded_filename,
            ),
        )

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

    def _get_measured_height_fallback_z(self, measured_height=None):
        try:
            measured_height = float(measured_height)
        except Exception:
            measured_height = None

        if measured_height is not None and measured_height > 0:
            return measured_height + 200.0

        return 450.0

    def _resolve_safe_resume_z(self, measured_height=None):
        if self._is_moonraker_mode():
            zmax = self._moonraker_toolhead_zmax()
            if zmax is not None:
                return dict(z=zmax, source="Moonraker toolhead.axis_maximum.z")
        else:
            zmax = self._get_printer_zmax()
            if zmax is not None:
                return dict(z=zmax, source="OctoPrint printer profile")

        override_zmax = self._get_z_max_override()
        if override_zmax is not None:
            return dict(z=override_zmax, source="z_max_override_mm")

        return dict(
            z=self._get_measured_height_fallback_z(measured_height=measured_height),
            source="measured print height + 200 mm",
        )

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

    def _get_assumed_position(self):
        return self._get_assumed_position_from_settings()

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

    def _save_global_settings(self):
        settings_obj = getattr(self._settings, "settings", None)
        if settings_obj is not None and hasattr(settings_obj, "save"):
            settings_obj.save()
            return

        self._settings.save()

    def _strip_managed_script_blocks(self, current_script):
        cleaned = current_script or ""
        removed = False
        for start_marker, end_marker in (
            (ASSUMED_POSITION_MARKER_START, ASSUMED_POSITION_MARKER_END),
            (LEGACY_MARKER_START, LEGACY_MARKER_END),
        ):
            pattern = re.compile(
                re.escape(start_marker) + r".*?" + re.escape(end_marker) + r"\s*",
                flags=re.S,
            )
            cleaned, count = pattern.subn("", cleaned)
            removed = removed or count > 0

        cleaned = cleaned.strip()
        return (cleaned + "\n" if cleaned else ""), removed

    def _script_only_plugin_cancel_shutdown(self, script_text):
        command_lines = []
        for line in (script_text or "").splitlines():
            command = line.split(";", 1)[0].strip()
            if not command:
                continue
            command_lines.append(re.sub(r"\s+", " ", command.upper()))

        if not command_lines:
            return False

        return all(command in PLUGIN_CANCEL_SHUTDOWN_COMMANDS for command in command_lines)

    def cleanup_assumed_position_scripts(self):
        done_script = self._settings.global_get(["scripts", "gcode", "afterPrintDone"]) or ""
        cancelled_script = self._settings.global_get(["scripts", "gcode", "afterPrintCancelled"]) or ""
        cleaned_done, done_removed = self._strip_managed_script_blocks(done_script)
        cleaned_cancelled, cancelled_removed = self._strip_managed_script_blocks(cancelled_script)

        if cancelled_removed and self._script_only_plugin_cancel_shutdown(cleaned_cancelled):
            cleaned_cancelled = ""

        changed = False
        if done_removed and cleaned_done != done_script:
            self._settings.global_set(["scripts", "gcode", "afterPrintDone"], cleaned_done)
            changed = True
        if cancelled_removed and cleaned_cancelled != cancelled_script:
            self._settings.global_set(["scripts", "gcode", "afterPrintCancelled"], cleaned_cancelled)
            changed = True

        if changed:
            self._save_global_settings()

        self._settings.set(["smart_park_enabled"], False)
        self._settings.save()

    def _format_gcode_value(self, value):
        formatted = "{:.3f}".format(float(value))
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        return formatted


__plugin_name__ = "OctoGoat"
__plugin_version__ = "0.1.0"
__plugin_author__ = "Lazarus / OctoGoat"
__plugin_url__ = "https://YOURDOMAIN.COM/octogoat"
__plugin_license__ = "Proprietary - See LICENSE.txt"
__plugin_privacypolicy__ = "https://YOURDOMAIN.COM/privacy"
__plugin_pythoncompat__ = ">=3.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = OctoGoatPlugin()
