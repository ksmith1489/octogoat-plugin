$(function () {
  function OctoGoatViewModel(parameters) {
    var self = this;

    self.settingsViewModel = parameters[0];

    self.confirmed = ko.observable(false);

    // These keep tab bindings alive even before we wire real values
    self.freeResumesRemaining = ko.observable(3);
    self.licenseValid = ko.observable(true);

    self.resumePrint = function () {
      // minimal: just hit plugin API so we know wiring works
      OctoPrint.simpleApiCommand("octoprint_octogoat", "ping", {})
        .done(function (resp) {
          new PNotify({
            title: "OctoGOAT",
            text: "Ping OK",
            type: "success"
          });
        })
        .fail(function () {
          new PNotify({
            title: "OctoGOAT",
            text: "Ping failed",
            type: "error"
          });
        });

      return false;
    };

    self.testOctoGoatConnection = function () {
      OctoPrint.simpleApiCommand("octoprint_octogoat", "ping", {})
        .done(function () {
          new PNotify({
            title: "OctoGOAT",
            text: "Engine ping OK",
            type: "success"
          });
        })
        .fail(function () {
          new PNotify({
            title: "OctoGOAT",
            text: "Engine ping failed",
            type: "error"
          });
        });

      return false;
    };

    self.onStartupComplete = function () {
      console.log("OctoGoat loaded");
    };
  }

  OCTOPRINT_VIEWMODELS.push({
    construct: OctoGoatViewModel,
    dependencies: ["settingsViewModel"],
    elements: ["#tab_plugin_octoprint_octogoat", "#settings_plugin_octoprint_octogoat"]
  });
});