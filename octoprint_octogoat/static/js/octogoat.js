$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];

        // ---- Safe access pattern ----
        self.pluginSettings = function () {
            return self.settingsViewModel.settings.plugins.octoprint_octogoat;
        };

        self.confirmed = ko.observable(false);

        self.freeResumesRemaining = ko.observable(0);
        self.licenseValid = ko.observable(false);

        self.onBeforeBinding = function () {
            var ps = self.pluginSettings();

            self.freeResumesRemaining(ps.free_resumes_remaining());
            self.licenseValid(ps.cached_valid());
        };

        // -----------------------------
        // ANALYZE
        // -----------------------------
        self.analyze = function () {
            OctoPrint.simpleApiCommand("octoprint_octogoat", "analyze", {
                firmware: "klipper",
                mph: 10,      // temporary test values
                lh: 0.2
            }).done(function (response) {

                if (!response.ok) {
                    new PNotify({
                        title: "Analyze Error",
                        text: response.error || "Unknown error",
                        type: "error"
                    });
                    return;
                }

                new PNotify({
                    title: "Analyze Success",
                    text: "Resume height: " + response.resume_z,
                    type: "success"
                });

            }).fail(function () {
                new PNotify({
                    title: "Server Error",
                    text: "Analyze failed",
                    type: "error"
                });
            });
        };

        // -----------------------------
        // SAVE ONLY
        // -----------------------------
        self.saveResume = function () {
            OctoPrint.simpleApiCommand("octoprint_octogoat", "save_resume_file", {})
                .done(function (response) {

                    if (!response.ok) {
                        new PNotify({
                            title: "Error",
                            text: response.error,
                            type: "error"
                        });
                        return;
                    }

                    self.freeResumesRemaining(response.free_remaining);

                    new PNotify({
                        title: "Saved",
                        text: response.filename,
                        type: "success"
                    });
                });
        };

        // -----------------------------
        // RESUME NOW
        // -----------------------------
        self.resumeNow = function () {
            OctoPrint.simpleApiCommand("octoprint_octogoat", "resume_now", {})
                .done(function (response) {

                    if (!response.ok) {
                        new PNotify({
                            title: "Error",
                            text: response.error,
                            type: "error"
                        });
                        return;
                    }

                    new PNotify({
                        title: "Printing",
                        text: "Resume started",
                        type: "success"
                    });
                });
        };
    }

    OCTOPRINT_VIEWMODELS.push([
        OctoGoatViewModel,
        ["settingsViewModel"],
        ["#tab_plugin_octoprint_octogoat"]
    ]);
});