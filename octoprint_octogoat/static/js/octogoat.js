$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];

        self.licenseValid = ko.observable(false);
        self.printerReady = ko.observable(false);
        self.fileLoaded = ko.observable(false);

        self.measuredHeight = ko.observable("");
        self.layerHeight = ko.observable("");

        self.resumeBuilt = ko.observable(false);

        self.resumeZ = ko.observable("");
        self.datumX = ko.observable("");
        self.datumY = ko.observable("");
        self.datumZ = ko.observable("");
        self.safeDatumZ = ko.observable("");
        self.parkX = ko.observable("");
        self.parkY = ko.observable("");
        self.parkZ = ko.observable("");
       
        self.previewText = ko.observable("");
        self.motionAcknowledged = ko.observable(false);

        function notify(title, text, type) {
            new PNotify({
                title: title,
                text: text,
                type: type || "info"
            });
        }

        function api(cmd, payload) {
            return OctoPrint.simpleApiCommand("octogoat", cmd, payload || {});
        }

        self.validateInputs = function () {
            var mph = parseFloat(self.measuredHeight());
            var lh = parseFloat(self.layerHeight());

            if (!mph || mph <= 0) {
                notify("Input Error", "Measured height required", "error");
                return false;
            }

            if (!lh || lh <= 0) {
                notify("Input Error", "Layer height required", "error");
                return false;
            }

            return true;
        };

        self.buildResume = function () {
            if (!self.validateInputs()) return;

            api("build_resume", {
                measured_height: parseFloat(self.measuredHeight()),
                layer_height: parseFloat(self.layerHeight())
            })
            .done(function (resp) {
                if (!resp || !resp.ok) {
                    notify("Error", resp && resp.error ? resp.error : "Resume build failed", "error");
                    return;
                }

                self.resumeZ(resp.resume_z || "");

                if (resp.datum) {
                    self.datumX(resp.datum.x != null ? resp.datum.x : "");
                    self.datumY(resp.datum.y != null ? resp.datum.y : "");
                    self.datumZ(resp.datum.z != null ? resp.datum.z : "");
                  
                    self.safeDatumZ(resp.datum.z + 10);
                }
                

                if (resp.park) {
                    self.parkX(resp.park.x != null ? resp.park.x : "");
                    self.parkY(resp.park.y != null ? resp.park.y : "");
                    self.parkZ(resp.park.z != null ? resp.park.z : "");
                }

                self.previewText(resp.preview ? resp.preview.join("\n") : "");
                self.motionAcknowledged(false);
                self.resumeBuilt(true);

                notify("Alignment Ready", "Move printer to quadrant corner then press Get Set.", "notice");
            })
            .fail(function () {
                notify("Error", "API request failed", "error");
            });
        };

        self.applyPark = function () {
            api("apply_park")
            .done(function () {
                notify("Park Position Set", "Toolhead reference position applied.", "success");
            })
            .fail(function () {
                notify("Error", "Park command failed", "error");
            });
        };

        self.goToDatum = function () {
            api("goto_datum", {
                x: self.datumX(),
                y: self.datumY(),
                z: self.datumZ()
            })
            .done(function () {
                notify("Move Complete", "Toolhead moved to alignment position.", "success");
            })
            .fail(function () {
                notify("Error", "Move failed", "error");
            });
        };

        self.lockDatum = function () {
            api("lock_datum", {
                x: self.datumX(),
                y: self.datumY(),
                z: self.datumZ()
            })
            .done(function () {
                notify("Alignment Locked", "True alignment point saved.", "success");
            })
            .fail(function () {
                notify("Error", "Lock failed", "error");
            });
        };

        self.resumeNow = function () {
            if (!self.motionAcknowledged()) {
                notify("Safety", "You must acknowledge printer motion", "notice");
                return;
            }

            api("execute_resume")
            .done(function (resp) {
                if (!resp || resp.ok !== true) {
                    notify("Error", resp && resp.error ? resp.error : "Resume failed", "error");
                    return;
                }
                notify("OctoGOAT", "Resume sequence started", "success");
            })
            .fail(function () {
                notify("Error", "Resume failed", "error");
            });
        };

        self.validateLicense = function () {
            api("validate")
            .done(function (resp) {
                self.licenseValid(resp && resp.valid === true);
            })
            .fail(function () {
                self.licenseValid(false);
            });
        };

        self.onBeforeBinding = function () {
            var script = document.createElement("script");
            script.src = "https://js.stripe.com/v3/pricing-table.js";
            script.async = true;
            document.body.appendChild(script);
        };

        $("#pricing-modal").on("shown.bs.modal", function () {
            var container = document.getElementById("pricing-table-container");
            if (!container) return;

            if (container.children.length === 0) {
                var installId = self.settingsViewModel.settings.plugins.octogoat.install_id();

                var table = document.createElement("stripe-pricing-table");
                table.setAttribute("pricing-table-id", "prctbl_1T6RDmE52GVAutfiaLKmlSue");
                table.setAttribute("publishable-key", "pk_live_51Se4ekE52GVAutfixtDzM2jB9edEZLVHIGm8EwPQ6IxZakas76Zu8xap83euJ56hnArtqEKPqS2yxwATen3yLcgn000er82jFv");
                table.setAttribute("client-reference-id", installId);

                container.appendChild(table);
            }
        });

        self.onStartupComplete = function () {
            self.validateLicense();
        };

        console.log("OctoGOAT ViewModel Loaded");
        
        self.onTabChange = function (current) {
            if (current === "#tab_plugin_octogoat") {
                self.validateLicense();
            }
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#tab_plugin_octogoat"]
    });

});