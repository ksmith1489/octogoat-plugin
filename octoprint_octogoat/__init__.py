import octoprint.plugin


class OctoGoatPlugin(
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
):

    def get_template_configs(self):
        return [
            dict(type="tab", name="OctoGoat"),
        ]

    def get_assets(self):
        return dict(
            js=["js/octogoat.js"]
        )

    def on_api_command(self, command, data):
        if command == "resume":
            return dict(success=True)

        if command == "ping":
            return dict(success=True)


__plugin_name__ = "OctoGoat"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = OctoGoatPlugin()
