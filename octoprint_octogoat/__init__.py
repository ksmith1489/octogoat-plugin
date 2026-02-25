# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import requests

# (keep imported if you need it later; not used in this refactor yet)
from .resume_engine import build_resumed_gcode


class OctoGoatPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
):

    # -----------------------
    # Settings
    # -----------------------

    def get_settings_defaults(self):
        return dict(
            api_key="",  # this is your LICENSE KEY
            engine_url="https://app.lazarus3dprint.com",
            free_resumes_remaining=1,
        )

    # -----------------------
    # Templates
    # -----------------------

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
                custom_bindings=False,  # IMPORTANT: keep settings simple + default-bound
            ),
        ]

    # -----------------------
    # Assets
    # -----------------------

    def get_assets(self):
        return dict(
            js=["js/octogoat.js"],
        )

    # -----------------------
    # Simple API
    # -----------------------

    def get_api_commands(self):
        return dict(
            ping=[],
            validate=["license_key"],
        )

    def on_api_command(self, command, data):

        if command == "ping":
            return dict(ok=True, message="OctoGoat API reachable")

        if command == "validate":
            license_key = (data or {}).get("license_key", "").strip()
            if not license_key:
                return dict(valid=False)

            engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
            validate_url = f"{engine_url}/validate"

            try:
                r = requests.post(
                    validate_url,
                    json={"license_key": license_key},
                    timeout=10,
                )
                if r.status_code != 200:
                    return dict(valid=False)
                payload = r.json() if r.content else {}
                return dict(valid=(payload.get("valid") is True))
            except Exception as exc:
                self._logger.error("License validation failed: %s", exc)
                return dict(valid=False)

        return None


__plugin_name__ = "OctoGoat"
__plugin_version__ = "0.1.0"
__plugin_pythoncompat__ = ">=3.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = OctoGoatPlugin()