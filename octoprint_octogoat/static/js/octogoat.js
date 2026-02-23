$(function () {
    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];
        self.settings = self.settingsViewModel.settings;   // <-- IMPORTANT

        self.confirmed = ko.observable(false);

        self.testConnection = function () {
            OctoPrint.simpleApiCommand("octogoat", "ping", {})
                .done(function (resp) {
                    alert(JSON.stringify(resp, null, 2));
                })
                .fail(function (jqXHR) {
                    var payload = jqXHR.responseJSON || { error: jqXHR.responseText || "Request failed" };
                    alert(JSON.stringify(payload, null, 2));
                });
        };

        self.resumePrint = function () {
            alert("Resume clicked (stub). Next step: wire this to build_resumed_gcode + job creation.");
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_octogoat", "#tab_plugin_octogoat"]
    });
});