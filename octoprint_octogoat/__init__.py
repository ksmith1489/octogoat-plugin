# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import requests
from .resume_engine import build_resumed_gcode


class OctoGoatPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
):

    ## -----------------------
    ## Settings
    ## -----------------------

    def get_settings_defaults(self):
        return dict(
            api_key="",
            engine_url="https://app.lazarus3dprint.com",
            free_resumes_remaining=1,
            license_valid=False,
        )

    ## -----------------------
    ## Templates
    ## -----------------------

    def get_template_configs(self):
        return [
            dict(
                type="generic",
                template="octogoat_generic.jinja2",
                custom_bindings=True,
            ),
            dict(
                type="settings",
                template="octogoat_settings.jinja2",
                custom_bindings=False,
            ),
        ]

    ## -----------------------
    ## Assets
    ## -----------------------

    def get_assets(self):
        return dict(
            js=["js/octogoat.js"],
        )

    ## -----------------------
    ## Simple API
    ## -----------------------

    def get_api_commands(self):
        return dict(
            ping=[],
            validate=["license_key"],
        )

    def on_api_command(self, command, data):

        if command == "ping":
            return dict(
                ok=True,
                message="OctoGoat API reachable"
            )

        if command == "validate":

            license_key = data.get("license_key")
            if not license_key:
                return dict(valid=False)

            engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
            validate_url = f"{engine_url}/validate"

            try:
                response = requests.post(
                    validate_url,
                    json={"license_key": license_key},
                    timeout=10,
                )

                if response.status_code == 200:
                    result = response.json()
                    return dict(valid=result.get("valid", False))
                else:
                    return dict(valid=False)

            except Exception as exc:
                self._logger.error(f"License validation failed: {exc}")
                return dict(valid=False)


__plugin_name__ = "OctoGoat"
__plugin_version__ = "0.1.0"
__plugin_pythoncompat__ = ">=3.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = OctoGoatPlugin()