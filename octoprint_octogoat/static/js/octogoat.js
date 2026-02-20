OCTOPRINT_VIEWMODELS.push({
    construct: function(parameters) {
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
            OctoPrint.simpleApiCommand("octoprint_octogoat", "resume", {})
                .done(function(response) {
                    if (response.locked) {
                        new PNotify({
                            title: "License Required",
                            text: "Please activate your license.",
                            type: "error"
                        });
                    } else if (response.error) {
                        new PNotify({
                            title: "Error",
                            text: response.error,
                            type: "error"
                        });
                    } else {
                        new PNotify({
                            title: "Resume Sent",
                            text: "Resume command sent successfully.",
                            type: "success"
                        });
                    }
                });
        };
    },
    dependencies: ["settingsViewModel"],
    elements: ["#octogoat-tab"]
});
