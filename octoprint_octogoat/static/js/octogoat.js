$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];

        self.licenseValid = ko.observable(false);

        self._getLicenseKey = function () {
            try {
                return (self.settingsViewModel.settings.plugins.octogoat.api_key() || "").trim();
            } catch (e) {
                return "";
            }
        };

        self.validateLicense = function () {
            var key = self._getLicenseKey();

            if (!key) {
                self.licenseValid(false);
                return;
            }

            OctoPrint.simpleApiCommand("octogoat", "validate", { license_key: key })
                .done(function (resp) {
                    self.licenseValid(resp && resp.valid === true);
                })
                .fail(function () {
                    self.licenseValid(false);
                });
        };

        self.openCheckout = function () {
            window.open("https://buy.stripe.com/7sYbJ18IfaFp4L7fjbenS05", "_blank");
        };

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

        // When the tab becomes visible, validate.
        self.onTabChange = function (current, previous) {
            if (current === "#tab_plugin_octogoat") {
                self.validateLicense();
            }
        };

        // Also validate once after startup
        self.onStartupComplete = function () {
            self.validateLicense();
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#tab_plugin_octogoat"]
    });

});