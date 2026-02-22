$(function() {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];

        self.confirmed = ko.observable(false);
        self.freeResumesRemaining = ko.observable(3);
        self.licenseValid = ko.observable(true);

        self.resumePrint = function() {
            OctoPrint.simpleApiCommand("octoprint_octogoat", "resume", {})
                .done(function(response) {
                    new PNotify({
                        title: "Resume",
                        text: "Resume triggered.",
                        type: "success"
                    });
                })
                .fail(function() {
                    new PNotify({
                        title: "Error",
                        text: "Resume failed.",
                        type: "error"
                    });
                });

            return false;
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"],
        elements: [
            "#tab_plugin_octoprint_octogoat",
            "#settings_plugin_octoprint_octogoat"
        ]
    });

});