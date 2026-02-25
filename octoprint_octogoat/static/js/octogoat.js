$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];

        self.confirmed = ko.observable(false);
        self.licenseValid = ko.observable(false);

        /* --------------------------
           ENGINE TEST
        ---------------------------*/

        self.testConnection = function () {
            OctoPrint.simpleApiCommand("octogoat", "ping", {})
                .done(function (resp) {
                    alert(JSON.stringify(resp, null, 2));
                })
                .fail(function () {
                    alert("Request failed");
                });
        };

        self.resumePrint = function () {
            alert("Resume clicked (stub).");
        };

        /* --------------------------
           LICENSE VALIDATION
        ---------------------------*/

        self.validateLicense = function () {

            var key = self.settingsViewModel.settings.plugins.octogoat.api_key();

            if (!key) {
                self.licenseValid(false);
                return;
            }

            OctoPrint.simpleApiCommand("octogoat", "validate", {
                license_key: key
            })
            .done(function (response) {
                self.licenseValid(response.valid === true);
            })
            .fail(function () {
                self.licenseValid(false);
            });
        };

        self.openCheckout = function () {
            window.open("https://lazarus3dprint.com/checkout", "_blank");
        };

        /* --------------------------
           LIFECYCLE
        ---------------------------*/

        self.onBeforeBinding = function () {
            self.validateLicense();
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"]
    });

});