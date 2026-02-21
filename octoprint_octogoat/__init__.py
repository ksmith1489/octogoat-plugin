import time
import requests
import octoprint.plugin


class OctoGoatPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.StartupPlugin,
):

    # ----------------------------
    # Startup (just for logging)
    # ----------------------------
    def on_after_startup(self):
        self._logger.info("OctoGoat loaded")

    # ----------------------------
    # Settings
    # ----------------------------
    def get_settings_defaults(self):
        return dict(
            api_key="",
            engine_url="https://app.lazarus3dprint.com",   # licensing/validation only (NOT resume engine)
            license_key="",
            free_resumes_remaining=3,
            cached_valid=False,
            last_validation_ts=0,

            # park position storage (optional)
            park_x=None,
            park_y=None,
            park_z=None,

            # optional: klipper park macro text name / command
            park_macro="END_PRINT",
        )

    # ----------------------------
    # Templates
    # ----------------------------
    def get_template_configs(self):
        return [
            dict(type="tab", name="OctoGoat", template="octogoat_tab.jinja2", custom_bindings=False),
            dict(type="settings", name="OctoGoat", template="octogoat_settings.jinja2", custom_bindings=False),
        ]

    # ----------------------------
    # Assets
    # ----------------------------
    def get_assets(self):
        return dict(
            js=["js/octogoat.js"],
        )

    # ----------------------------
    # Simple API
    # ----------------------------
    def get_api_commands(self):
        return dict(
            ping=[],
            resume=[],
            # next steps for horseblinder flow:
            analyze=["firmware", "mph", "lh"],
            set_park=[],
            move_to_datum=[],
            confirm_datum=[],
            save_resume_file=[],
            resume_now=[],
        )

    def on_api_command(self, command, data):
        if command == "ping":
            return self._handle_ping()

        if command == "resume":
            # temporary stub until we wire the 3-step flow
            return dict(ok=True)

        if command == "analyze":
            return dict(ok=False, error="analyze not implemented yet")

        if command == "set_park":
            return dict(ok=False, error="set_park not implemented yet")

        if command == "move_to_datum":
            return dict(ok=False, error="move_to_datum not implemented yet")

        if command == "confirm_datum":
            return dict(ok=False, error="confirm_datum not implemented yet")

        if command == "save_resume_file":
            return dict(ok=False, error="save_resume_file not implemented yet")

        if command == "resume_now":
            return dict(ok=False, error="resume_now not implemented yet")

        return dict(ok=False, error="unknown command")

    # ----------------------------
    # Helpers
    # ----------------------------
    def _handle_ping(self):
        # Ping is ONLY for your small Render service (license server), not resume engine.
        api_key = self._settings.get(["api_key"])
        engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
        try:
            r = requests.get(
                f"{engine_url}/api/ping",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            return dict(ok=r.ok, status=r.status_code)
        except Exception as exc:
            return dict(ok=False, error=str(exc))


__plugin_name__ = "OctoGoat"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = OctoGoatPlugin()