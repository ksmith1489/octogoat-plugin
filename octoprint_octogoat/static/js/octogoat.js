$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];

        /* --------------------------------------------------
           GLOBAL STATE
        -------------------------------------------------- */

        self.page = ko.observable(1);   // 1 = inputs, 2 = alignment, 3 = preview

        self.confirmed = ko.observable(false);
        self.expertConfirmed = ko.observable(false);

        self.mph = ko.observable("");
        self.lh = ko.observable("");
        self.firmware = ko.observable("klipper");

        self.currentFile = ko.observable("");

        self.resumePreview = ko.observable("");
        self.resumeZ = ko.observable(null);
        self.datum = ko.observable(null);

        self.freeResumesRemaining = ko.observable(
            self.settings.settings.plugins.octoprint_octogoat.free_resumes_remaining()
        );

        self.licenseValid = ko.observable(
            self.settings.settings.plugins.octoprint_octogoat.cached_valid()
        );

        /* --------------------------------------------------
           LOAD CURRENT FILE INFO
        -------------------------------------------------- */

        self.onBeforeBinding = function () {
            OctoPrint.job.get()
                .done(function (response) {
                    if (response && response.job && response.job.file) {
                        self.currentFile(response.job.file.name || "Unknown");
                    }
                });
        };

        /* --------------------------------------------------
           PAGE 1 → ANALYZE
        -------------------------------------------------- */

        self.proceedToAlignment = function (vm, event) {
            if (event) event.preventDefault();

            OctoPrint.simpleApiCommand("octoprint_octogoat", "analyze", {
                firmware: self.firmware(),
                mph: self.mph(),
                lh: self.lh()
            })
            .done(function (response) {

                if (!response.ok) {
                    new PNotify({
                        title: "Error",
                        text: response.error || "Analyze failed.",
                        type: "error"
                    });
                    return;
                }

                self.resumeZ(response.resume_z);
                self.resumePreview(response.preview.join("\n"));
                self.datum(response.datum);

                self.page(2);
            })
            .fail(function () {
                new PNotify({
                    title: "Server Error",
                    text: "Analyze failed.",
                    type: "error"
                });
            });

            return false;
        };

        /* --------------------------------------------------
           PAGE 2 → ALIGNMENT ACTIONS
        -------------------------------------------------- */

        self.moveToDatum = function (vm, event) {
            if (event) event.preventDefault();

            OctoPrint.simpleApiCommand("octoprint_octogoat", "move_to_datum", {})
                .done(function (response) {
                    if (!response.ok) {
                        new PNotify({
                            title: "Error",
                            text: response.error || "Move failed.",
                            type: "error"
                        });
                    }
                });

            return false;
        };

        self.confirmDatum = function (vm, event) {
            if (event) event.preventDefault();

            OctoPrint.simpleApiCommand("octoprint_octogoat", "confirm_datum", {})
                .done(function (response) {
                    if (!response.ok) {
                        new PNotify({
                            title: "Error",
                            text: response.error || "Confirm failed.",
                            type: "error"
                        });
                        return;
                    }

                    self.page(3);
                });

            return false;
        };

        self.skipToPreview = function (vm, event) {
            if (event) event.preventDefault();

            if (!self.expertConfirmed()) {
                new PNotify({
                    title: "Expert Confirmation Required",
                    text: "You must confirm coordinates are verified.",
                    type: "error"
                });
                return;
            }

            self.page(3);
            return false;
        };

        /* --------------------------------------------------
           PAGE 3 → SAVE + RESUME
        -------------------------------------------------- */

        self.saveResumeFile = function (vm, event) {
            if (event) event.preventDefault();

            OctoPrint.simpleApiCommand("octoprint_octogoat", "save_resume_file", {})
                .done(function (response) {

                    if (response.locked) {
                        new PNotify({
                            title: "License Required",
                            text: "Activate license to continue.",
                            type: "error"
                        });
                        return;
                    }

                    if (!response.ok) {
                        new PNotify({
                            title: "Error",
                            text: response.error || "Save failed.",
                            type: "error"
                        });
                        return;
                    }

                    if (response.free_remaining !== undefined) {
                        self.freeResumesRemaining(response.free_remaining);
                    }

                    new PNotify({
                        title: "Resume File Saved",
                        text: "File added to OctoPrint.",
                        type: "success"
                    });
                });

            return false;
        };

        self.resumeNow = function (vm, event) {
            if (event) event.preventDefault();

            if (!self.confirmed()) {
                new PNotify({
                    title: "Confirmation Required",
                    text: "You must confirm alignment and temps.",
                    type: "error"
                });
                return;
            }

            OctoPrint.simpleApiCommand("octoprint_octogoat", "resume_now", {})
                .done(function (response) {

                    if (!response.ok) {
                        new PNotify({
                            title: "Error",
                            text: response.error || "Resume failed.",
                            type: "error"
                        });
                        return;
                    }

                    new PNotify({
                        title: "Print Started",
                        text: "Resume print started.",
                        type: "success"
                    });
                });

            return false;
        };

        /* --------------------------------------------------
           NAVIGATION
        -------------------------------------------------- */

        self.goBack = function () {
            if (self.page() === 3) {
                self.page(2);
            } else if (self.page() === 2) {
                self.page(1);
            }
        };
    }

    OCTOPRINT_VIEWMODELS.push([
        OctoGoatViewModel,
        ["settingsViewModel"],
        ["#tab_plugin_octoprint_octogoat"]
    ]);

});