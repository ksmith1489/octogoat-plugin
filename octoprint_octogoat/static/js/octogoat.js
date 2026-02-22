$(function() {

    function OctoGoatViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];

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
       
	    };

        self.onStartupComplete = function () {
            self.setupUI();
        };		
        
      
   	OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#gen_plugin_octoprint_octogoat"]
        });

    
