$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];

        self.confirmed = ko.observable(false);

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

        self.licenseValid = ko.observable(false);

        self.validateLicense = function () {

            var key = self.settingsViewModel.settings.plugins.octogoat.api_key();

            if (!key) {
                self.licenseValid(false);
                return;
            }

            $.ajax({
                url: "https://app.lazarus3dprint.com/validate",
                method: "POST",
                contentType: "application/json",
                data: JSON.stringify({
                    license_key: key
                }),
                success: function (response) {
                    self.licenseValid(response.valid === true);
                },
                error: function () {
                    self.licenseValid(false);
                }
            });
        };

        self.openCheckout = function () {
            window.open("https://lazarus3dprint.com/checkout", "_blank");
        };

        self.onBeforeBinding = function () {
            self.validateLicense();
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"]
    });

});