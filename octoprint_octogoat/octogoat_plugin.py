import time
import requests
import octoprint.plugin


class OctoGoatPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.SimpleApiPlugin,
):

    # ----------------------------
    # Settings
    # ----------------------------

    def get_settings_defaults(self):
        return dict(
            api_key="",
            engine_url="https://app.lazarus3dprint.com",
            license_key="",
            free_resumes_remaining=3,
            last_validation_ts=0,
            cached_valid=False,
        )

    # ----------------------------
    # Assets (JS only)
    # ----------------------------

    def get_assets(self):
        return dict(
            js=["js/octogoat.js"],
        )

    # ----------------------------
    # Template Registration
    # ----------------------------

    def get_template_configs(self):
        return [
            dict(
                type="settings",
                name="OctoGoat",
                template="octogoat_settings.jinja2",
                custom_bindings=False,
            ),
            dict(
                type="tab",
                name="OctoGoat",
                template="octogoat_tab.jinja2",
                custom_bindings=False,
            ),
        ]

    # ----------------------------
    # API Commands
    # ----------------------------

    def get_api_commands(self):
        return dict(
            ping=[],
            resume=["layer_height", "print_height", "firmware"],
        )

    def on_api_command(self, command, data):
        if command == "ping":
            return self._handle_ping()

        if command == "resume":
            return self._handle_resume(data)

        return None

    # ----------------------------
    # Ping
    # ----------------------------

    def _handle_ping(self):
        api_key = self._settings.get(["api_key"])
        engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")

        try:
            response = requests.get(
                f"{engine_url}/api/ping",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            return {"ok": response.ok}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ----------------------------
    # License Validation
    # ----------------------------

    def _is_license_valid(self):
        license_key = self._settings.get(["license_key"])
        cached_valid = self._settings.get(["cached_valid"])
        last_validation_ts = self._settings.get(["last_validation_ts"])

        now = time.time()

        # 72 hour cached validity
        if cached_valid and (now - last_validation_ts) < (72 * 3600):
            return True

        if not license_key:
            return False

        try:
            response = requests.post(
                "https://app.lazarus3dprint.com/validate",
                json={"license_key": license_key},
                timeout=5,
            )

            if response.ok and response.json().get("valid"):
                self._settings.set(["cached_valid"], True)
                self._settings.set(["last_validation_ts"], now)
                self._settings.save()
                return True

        except Exception:
            # 7-day grace if previously valid
            if cached_valid and (now - last_validation_ts) < (7 * 24 * 3600):
                return True

        self._settings.set(["cached_valid"], False)
        self._settings.save()
        return False

    # ----------------------------
    # Resume Handler
    # ----------------------------

    def _handle_resume(self, data):

        # License gate
        if not self._is_license_valid():
            free_left = self._settings.get(["free_resumes_remaining"]) or 0

            if free_left > 0:
                free_left -= 1
                self._settings.set(["free_resumes_remaining"], free_left)
                self._settings.save()
            else:
                return {"error": "License required", "locked": True}

        api_key = self._settings.get(["api_key"])
        engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")

        try:
            response = requests.post(
                f"{engine_url}/api/jobs",
                headers={"Authorization": f"Bearer {api_key}"},
                data=dict(
                    layer_height=data.get("layer_height"),
                    print_height=data.get("print_height"),
                    firmware=data.get("firmware"),
                    user_confirm_nozzle_above_print="true",
                ),
                timeout=30,
            )

            return response.json()

        except Exception as exc:
            return {"error": str(exc)}