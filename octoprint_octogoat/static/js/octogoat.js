$(function () {
    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];
        self.confirmed = ko.observable(false);

        self.testConnection = function () {
            OctoPrint.simpleApiCommand("octogoat", "ping", {})
                .done(function (resp) {
                    alert(JSON.stringify(resp, null, 2));
                })
                .fail(function (jqXHR) {
                    alert("Request failed");
                });
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_octogoat"]
    });
});