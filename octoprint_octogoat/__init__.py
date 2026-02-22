import io
import os
import time
import requests

import octoprint.plugin
from octoprint.filemanager import FileDestinations

from .resume_engine import build_resumed_gcode


class OctoGoatPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.StartupPlugin,
):
    def on_after_startup(self):
        self._logger.info("OctoGoat loaded")
        self._analysis_cache = None  # holds last analyze result

    # ----------------------------
    # Settings
    # ----------------------------
    def get_settings_defaults(self):
        return dict(
            # license/validator service only (Render)
            api_key="",
            engine_url="https://app.lazarus3dprint.com",
            license_key="",

            # free use gating
            free_resumes_remaining=3,

            # license cache
            cached_valid=False,
            last_validation_ts=0,
        )

    # ----------------------------
    # Templates / Assets
    def get_template_configs(self):
        return [
            dict(
                type="tab",
                name="OctoGoat",
                template="octogoat_tab.jinja2",
                custom_bindings=False,
            ),
            dict(
                type="settings",
                name="OctoGoat",
                template="octogoat_settings.jinja2",
                custom_bindings=False,
            ),
        ]
   
    def get_assets(self):
        return dict(js=["js/octogoat.js"])
     
    # ----------------------------
    # API
    # ----------------------------
    def get_api_commands(self):
        return dict(
            ping=[],
            analyze=["firmware", "mph", "lh"],
            save_resume_file=[],
            resume_now=[],

            # wired later (alignment commands)
            move_to_datum=[],
            confirm_datum=[],
            set_park=[],
        )

    def on_api_command(self, command, data):
        if command == "ping":
            return self._handle_ping()

        if command == "analyze":
            return self._handle_analyze(data)

        if command == "save_resume_file":
            return self._handle_save_resume_file(start_print=False)

        if command == "resume_now":
            return self._handle_save_resume_file(start_print=True)

        # placeholders for later wiring
        if command in ("move_to_datum", "confirm_datum", "set_park"):
            return dict(ok=False, error=f"{command} not implemented yet")

        return dict(ok=False, error="unknown command")

    # ----------------------------
    # License gating
    # ----------------------------
    def _is_license_valid(self) -> bool:
        license_key = (self._settings.get(["license_key"]) or "").strip()
        cached_valid = bool(self._settings.get(["cached_valid"]))
        last_ts = float(self._settings.get(["last_validation_ts"]) or 0)

        now = time.time()

        # cached valid within 72h
        if cached_valid and (now - last_ts) < (72 * 3600):
            return True

        if not license_key:
            return False

        engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
        try:
            r = requests.post(
                f"{engine_url}/validate",
                json={"license_key": license_key},
                timeout=8,
            )
            ok = bool(r.ok and r.json().get("valid") is True)
            if ok:
                self._settings.set(["cached_valid"], True)
                self._settings.set(["last_validation_ts"], now)
                self._settings.save()
                return True
        except Exception:
            # 7-day grace if previously valid
            if cached_valid and (now - last_ts) < (7 * 24 * 3600):
                return True

        self._settings.set(["cached_valid"], False)
        self._settings.save()
        return False

    def _consume_free_resume_if_needed(self) -> dict:
        if self._is_license_valid():
            return dict(ok=True, licensed=True, free_remaining=self._settings.get(["free_resumes_remaining"]) or 0)

        free_left = int(self._settings.get(["free_resumes_remaining"]) or 0)
        if free_left > 0:
            free_left -= 1
            self._settings.set(["free_resumes_remaining"], free_left)
            self._settings.save()
            return dict(ok=True, licensed=False, free_remaining=free_left)

        return dict(ok=False, locked=True, error="License required", free_remaining=0)

    # ----------------------------
    # Handlers
    # ----------------------------
    def _handle_ping(self):
        api_key = (self._settings.get(["api_key"]) or "").strip()
        engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
        try:
            r = requests.get(
                f"{engine_url}/api/ping",
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                timeout=10,
            )
            return dict(ok=r.ok, status=r.status_code)
        except Exception as exc:
            return dict(ok=False, error=str(exc))

    def _get_current_job_local_path(self):
        job = self._printer.get_current_job()
        if not job or "file" not in job or not job["file"]:
            raise ValueError("No active job/file found.")
        origin = job["file"].get("origin")
        if origin != "local":
            raise ValueError("Current file is not a LOCAL file (SD not supported for resume).")

        # In OctoPrint job dict this is usually the path relative to LOCAL
        relpath = job["file"].get("path") or job["file"].get("name")
        if not relpath:
            raise ValueError("Could not determine current file path.")

        disk_path = self._file_manager.path_on_disk(FileDestinations.LOCAL, relpath)
        if not os.path.exists(disk_path):
            raise ValueError("Local G-code file not found on disk.")
        return relpath, disk_path

    def _handle_analyze(self, data):
        firmware = (data.get("firmware") or "klipper").strip().lower()
        mph = float(str(data.get("mph") or "").strip())
        lh = float(str(data.get("lh") or "").strip())

        relpath, disk_path = self._get_current_job_local_path()

        with open(disk_path, "r", encoding="utf-8", errors="ignore") as f:
            original_text = f.read()

        result = build_resumed_gcode(
            original_text,
            firmware=firmware,
            layer_height_mm=lh,
            print_height_mm=mph,
        )

        # cache result in RAM (horseblinder separation)
        self._analysis_cache = dict(
            relpath=relpath,
            original_name=os.path.splitext(os.path.basename(relpath))[0],
            firmware=firmware,
            lh=lh,
            mph=mph,
            resume_z=result["resume_z"],
            datum=result["datum"],
            preview=result["preview"],
            resumed_text=result["resumed_text"],
        )

        return dict(
            ok=True,
            resume_z=result["resume_z"],
            datum=result["datum"],
            preview=result["preview"],
        )

    def _handle_save_resume_file(self, start_print: bool):
        if not self._analysis_cache:
            return dict(ok=False, error="Nothing to save yet. Run Analyze first.")

        gate = self._consume_free_resume_if_needed()
        if not gate.get("ok"):
            return dict(ok=False, locked=True, error=gate.get("error"), free_remaining=gate.get("free_remaining", 0))

        original_base = self._analysis_cache["original_name"]
        new_filename = f"{original_base}_OctoGOAT_resume.gcode"

        resumed_text = self._analysis_cache["resumed_text"]

        # Save to LOCAL ROOT
        self._file_manager.add_file(
            FileDestinations.LOCAL,
            new_filename,
            io.BytesIO(resumed_text.encode("utf-8")),
            allow_overwrite=True,
        )

        if start_print:
            # Select & print
            self._printer.select_file(new_filename, False, printAfterSelect=True)

        return dict(
            ok=True,
            started=bool(start_print),
            filename=new_filename,
            free_remaining=gate.get("free_remaining", 0),
            licensed=gate.get("licensed", False),
        )


__plugin_name__ = "OctoGoat"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = OctoGoatPlugin()