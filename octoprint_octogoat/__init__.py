# coding=utf-8
from __future__ import absolute_import

import os
import time
import uuid
import requests
import octoprint.plugin

from .resume_engine import build_resumed_gcode


WEEK_SECONDS = 7 * 24 * 60 * 60


class OctoGoatPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
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
            park_z_offset=30.0,
            safe_z_hop=10.0,
        )

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
            css=["css/octogoat.css"]
        )

    def get_api_commands(self):
        return dict(
            ping=[],
            validate=[],
            build_resume=["measured_height", "layer_height"],
            apply_park=[],
            goto_datum=["x", "y", "z"],
            lock_datum=["x", "y", "z"],
            execute_resume=[],
        )

    def on_api_command(self, command, data):

        if command == "ping":
            return dict(ok=True)

        if command == "validate":
            install_id = self._settings.get(["install_id"])
            last_validated = int(self._settings.get(["last_validated"]) or 0)
            engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
            validate_url = f"{engine_url}/validate"
            now = int(time.time())

            if last_validated and (now - last_validated) < WEEK_SECONDS:
                return dict(valid=True)

            try:
                r = requests.post(
                    validate_url,
                    json={"install_id": install_id},
                    timeout=5,
                )

                if r.status_code != 200:
                    return dict(valid=False)

                payload = r.json()
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
                layer_height = float(data.get("layer_height"))
            except Exception:
                return dict(ok=False, error="Invalid inputs")

            current = self._printer.get_current_data()
            if not current or not current.get("job") or not current["job"].get("file"):
                return dict(ok=False, error="No file selected")

            file_path = current["job"]["file"]["path"]
            if not file_path:
                return dict(ok=False, error="No file selected")

            try:
                absolute_path = self._file_manager.path_on_disk("local", file_path)
                with open(absolute_path, "r", encoding="utf-8", errors="replace") as f:
                    gcode_text = f.read()
            except Exception as e:
                return dict(ok=False, error="File read failed: %s" % e)

            try:
                result = build_resumed_gcode(
                    original_gcode_text=gcode_text,
                    firmware=self._settings.get(["firmware_type"]),
                    layer_height_mm=layer_height,
                    print_height_mm=measured_height,
                )
            except Exception as e:
                return dict(ok=False, error=str(e))

            park_x = float(self._settings.get(["park_x"]))
            park_y = float(self._settings.get(["park_y"]))
            profile = self._printer_profile_manager.get_current()
            zmax = float(profile["volume"]["height"])
            z_offset = float(self._settings.get(["park_z_offset"]))
            park_z = zmax - z_offset

            self._resume_cache = result["resumed_text"]

            return dict(
                ok=True,
                resume_z=result["resume_z"],
                datum=result["datum"],
                preview=result["preview"],
                park=dict(
                    x=park_x,
                    y=park_y,
                    z=park_z,
                ),
            )

        if command == "apply_park":
            firmware = self._settings.get(["firmware_type"])
            park_x = float(self._settings.get(["park_x"]))
            park_y = float(self._settings.get(["park_y"]))

            profile = self._printer_profile_manager.get_current()
            zmax = float(profile["volume"]["height"])
            z_offset = float(self._settings.get(["park_z_offset"]))
            park_z = zmax - z_offset

            if firmware == "klipper":
                cmd = f"SET_KINEMATIC_POSITION X={park_x} Y={park_y} Z={park_z}"
            else:
                cmd = f"G92 X{park_x} Y{park_y} Z{park_z}"

            self._printer.commands(cmd)
            return dict(ok=True)

        if command == "goto_datum":
            x = float(data.get("x"))
            y = float(data.get("y"))
            z = float(data.get("z"))
            safe_hop = float(self._settings.get(["safe_z_hop"]))

            cmds = [
                "G90",
                f"G0 Z{z + safe_hop}",
                f"G0 X{x} Y{y}",
            ]

            self._printer.commands(cmds)
            return dict(ok=True)

        if command == "lock_datum":
            firmware = self._settings.get(["firmware_type"])
            x = float(data.get("x"))
            y = float(data.get("y"))
            z = float(data.get("z"))

            if firmware == "klipper":
                cmd = f"SET_KINEMATIC_POSITION X={x} Y={y} Z={z}"
            else:
                cmd = f"G92 X{x} Y{y} Z{z}"

            self._printer.commands(cmd)

            if firmware == "klipper":
                self._printer.commands("G90")
                self._printer.commands(f"G0 Z{z + 10}")
            else:
                self._printer.commands("G90")
                self._printer.commands(f"G0 Z{z + 10}")

            return dict(ok=True)

        if command == "execute_resume":
            if not hasattr(self, "_resume_cache"):
                return dict(ok=False, error="No resume built")

            self._printer.commands("M400")
            self._printer.commands(self._resume_cache.splitlines())
            return dict(ok=True)

        return None

    def on_after_startup(self):
        try:
            self.install_smart_park()
        except Exception as e:
            self._logger.error("Smart park install failed: %s" % e)

        self._logger.info("OctoGOAT loaded successfully")
        self._logger.info("OctoGOAT plugin active")
    
    def install_smart_park(self):
        park_x = float(self._settings.get(["park_x"]))
        park_y = float(self._settings.get(["park_y"]))
        z_offset = float(self._settings.get(["park_z_offset"]))

        profile = self._printer_profile_manager.get_current()
        zmax = float(profile["volume"]["height"])
        park_z = zmax - z_offset

        marker_start = "; --- OctoGOAT Smart Park ---"
        marker_end = "; --- End OctoGOAT Smart Park ---"

        script = (
            f"{marker_start}\n"
            f"G90\n"
            f"G0 Z{park_z}\n"
            f"G0 X{park_x} Y{park_y}\n"
            f"{marker_end}"
        )

        current_script = self._settings.global_get(["scripts", "gcode", "afterPrintCancelled"]) or ""

        if marker_start in current_script:
            self._logger.info("OctoGOAT smart park already present, skipping insert")
            return

        new_script = current_script.rstrip() + "\n\n" + script + "\n"

        self._settings.global_set(["scripts", "gcode", "afterPrintCancelled"], new_script)
        self._settings.global_save()

        self._settings.set(["smart_park_enabled"], True)
        self._settings.save()

        self._logger.info("OctoGOAT smart park inserted successfully")


__plugin_name__ = "OctoGOAT"
__plugin_version__ = "0.1.0"
__plugin_pythoncompat__ = ">=3.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = OctoGoatPlugin()