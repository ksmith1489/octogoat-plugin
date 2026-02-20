$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];

        self.confirmed = ko.observable(false);

        self.resumePrint = function () {
            OctoPrint.simpleApiCommand("octoprint_octogoat", "resume", {})
                .done(function (response) {
                    new PNotify({
                        title: "Resume",
                        text: "Resume command sent",
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
