import requests

import time

import octoprint.plugin


class OctoGoatPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.SimpleApiPlugin,
):
    def get_settings_defaults(self):
        return {
            "api_key": "",
            "engine_url": "https://app.lazarus3dprint.com",
            "license_key": "",
            "free_resumes_remaining": 3,
            "last_validation_ts": 0,
            "cached_valid": False,
        }
    
    def get_assets(self):
    return {
        "js": ["js/octogoat.js"],
    }

    
    
    def _handle_ping(self):
        api_key = self._settings.get(["api_key"])
        engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
        ping_url = f"{engine_url}/api/ping"

        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = requests.get(ping_url, headers=headers, timeout=10)
            return {"ok": response.ok}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    

    def _is_license_valid(self):
        license_key = self._settings.get(["license_key"])
        cached_valid = self._settings.get(["cached_valid"])
        last_validation_ts = self._settings.get(["last_validation_ts"])

        # If cached and within 72 hours
        if cached_valid and (time.time() - last_validation_ts) < (72 * 3600):
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
                self._settings.set(["last_validation_ts"], time.time())
                self._settings.save()
                return True
        except Exception:
            # allow 7 day grace if previously valid
            if cached_valid and (time.time() - last_validation_ts) < (7 * 24 * 3600):
                return True

        self._settings.set(["cached_valid"], False)
        self._settings.save()
        return False

    def get_api_commands(self):
        return {
            "ping": [],
        }   "resume": ["layer_height", "print_height", "firmware"],

    def on_api_command(self, command, data):
        if command == "ping":
            return self._handle_ping()

        if command == "resume":
            return self._handle_resume(data)

        return None
    def _handle_resume(self, data):
        if not self._is_license_valid():
            free_left = self._settings.get(["free_resumes_remaining"]) or 0

            if free_left > 0:
                self._settings.set(["free_resumes_remaining"], free_left - 1)
                self._settings.save()
            else:
                return {"error": "License required", "locked": True}

        # Call backend resume API
        api_key = self._settings.get(["api_key"])
        engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")

        try:
            response = requests.post(
                f"{engine_url}/api/jobs",
                headers={"Authorization": f"Bearer {api_key}"},
                data={
                    "layer_height": data.get("layer_height"),
                    "print_height": data.get("print_height"),
                    "firmware": data.get("firmware"),
                    "user_confirm_nozzle_above_print": "true",
            },
                timeout=30,
        )
            return response.json()
        except Exception as exc:
            return {"error": str(exc)}



       

    def get_template_configs(self):
         {
            "type": "settings",
            "name": "OctoGoat",
            "template": "octogoat_settings.jinja2",
            "custom_bindings": True,
        },
        {
            "type": "tab",
            "name": "OctoGoat",
            "template": "octogoat_tab.jinja2",
            "custom_bindings": True,
        },
    ]