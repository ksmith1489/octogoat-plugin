$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];

        self.confirmed = ko.observable(false);

        self.freeResumesRemaining = ko.observable(
            self.settings.settings.plugins.octoprint_octogoat.free_resumes_remaining()
        );

        self.licenseValid = ko.observable(
            self.settings.settings.plugins.octoprint_octogoat.cached_valid()
        );

        self.resumePrint = function (vm, event) {
            if (event && event.preventDefault) event.preventDefault();

            OctoPrint.simpleApiCommand("octoprint_octogoat", "resume", {})
                .done(function (response) {

                    if (response.locked) {
                        new PNotify({
                            title: "License Required",
                            text: "Activate license to continue.",
                            type: "error"
                        });
                        return;
                    }

                    if (response.error) {
                        new PNotify({
                            title: "Error",
                            text: response.error,
                            type: "error"
                        });
                        return;
                    }

                    if (response.free_remaining !== undefined) {
                        self.freeResumesRemaining(response.free_remaining);
                    }

                    new PNotify({
                        title: "Resume Sent",
                        text: "Resume command executed.",
                        type: "success"
                    });

                })
                .fail(function () {
                    new PNotify({
                        title: "Server Error",
                        text: "Could not reach engine.",
                        type: "error"
                    });
                });

            return false;
        };
    }

    OCTOPRINT_VIEWMODELS.push([
        OctoGoatViewModel,
        ["settingsViewModel"],
        ["#tab_plugin_octoprint_octogoat"]
    ]);

});