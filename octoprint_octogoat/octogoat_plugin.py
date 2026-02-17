import requests

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
        }

    def get_api_commands(self):
        return {
            "ping": [],
        }

    def on_api_command(self, command, data):
        if command != "ping":
            return None

        api_key = self._settings.get(["api_key"])
        engine_url = (self._settings.get(["engine_url"]) or "").rstrip("/")
        ping_url = f"{engine_url}/api/ping"

        headers = {
            "Authorization": f"Bearer {api_key}",
        }

        status = None
        body = None
        ok = False

        try:
            response = requests.get(ping_url, headers=headers, timeout=10)
            status = response.status_code
            ok = response.ok
            try:
                body = response.json()
            except ValueError:
                body = response.text
        except requests.RequestException as exc:
            body = str(exc)

        return {
            "ok": ok,
            "status": status,
            "body": body,
        }

    def get_template_configs(self):
        return [
            {
                "type": "settings",
                "name": "OctoGoat",
                "custom_bindings": True,
            }
        ]
