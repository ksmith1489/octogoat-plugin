$(function() {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];

        self.confirmed = ko.observable(false);

        self.resumePrint = function() {
            OctoPrint.simpleApiCommand("octoprint_octogoat", "resume", {})
                .done(function(response) {
                    new PNotify({
                        title: "Resume",
                        text: "Resume triggered.",
                        type: "success"
                    });
                })
                .fail(function() {
                    new PNotify({
                        title: "Error",
                        text: "Resume failed.",
                        type: "error"
                    });
                });
        };
    }

    // IMPORTANT: Do NOT wrap this in any extra closures
    OCTOPRINT_VIEWMODELS.push([
        OctoGoatViewModel,
        ["settingsViewModel"],
        ["#tab_plugin_octoprint_octogoat"]
    ]);
});