$(function() {
    function OctogoatViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];

        self.confirmed = ko.observable(false);
        self.freeResumesRemaining = ko.observable(
            self.settings.settings.plugins.octoprint_octogoat.free_resumes_remaining()
        );
        self.licenseValid = ko.observable(
            self.settings.settings.plugins.octoprint_octogoat.cached_valid()
        );

        self.resumePrint = function() {
            OctoPrint.simpleApiCommand("octoprint_octogoat", "resume", {
                layer_height: 0.2,   // replace later with real inputs
                print_height: 5.0,
                firmware: "klipper"
            }).done(function(response) {
                if (response.locked) {
                    alert("License required.");
                } else if (response.error) {
                    alert(response.error);
                } else {
                    alert("Resume sent.");
                }
            });
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctogoatViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#octogoat-tab"]
    });
});
