$(function() {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];

        self.confirmed = ko.observable(false);

        // Dummy placeholders so bindings don’t explode
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

        self.onStartupComplete = function () {
            console.log("OctoGoat loaded");
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#gen_plugin_octogoat"]
    });

});