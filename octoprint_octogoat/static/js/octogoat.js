$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;
        var localFileInputSelector = "#octogoat-local-file-input";
        var dropzoneSelector = "#tab_plugin_octogoat .octogoat-file-dropzone";

        self.settingsViewModel = parameters[0];

        self.licenseValid = ko.observable(false);
        self.measuredHeight = ko.observable("");
        self.alignmentSide = ko.observable("left");

        self.resumeBuilt = ko.observable(false);
        self.resumeZ = ko.observable("");
        self.datumX = ko.observable("");
        self.datumY = ko.observable("");
        self.datumZ = ko.observable("");
        self.parkX = ko.observable("");
        self.parkY = ko.observable("");
        self.parkZ = ko.observable("");
        self.previewText = ko.observable("");
        self.motionAcknowledged = ko.observable(false);

        self.availableFiles = ko.observableArray([]);
        self.selectedServerFilePath = ko.observable("");
        self.selectedFileLabel = ko.observable("no file selected");
        self.selectedSourceType = ko.observable("");
        self.uploadedGcodeText = ko.observable("");
        self.uploadedFileName = ko.observable("");
        self.isDraggingFile = ko.observable(false);

        self.userSelectedFile = false;

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

        function resetResumeState() {
            self.resumeBuilt(false);
            self.resumeZ("");
            self.datumX("");
            self.datumY("");
            self.datumZ("");
            self.previewText("");
            self.motionAcknowledged(false);
        }

        function isSupportedGcodeName(name) {
            var lower = (name || "").toLowerCase();
            return lower.endsWith(".gcode") ||
                lower.endsWith(".gco") ||
                lower.endsWith(".gc") ||
                lower.endsWith(".g");
        }

        function setSelectedOctoPrintFile(path, label, isUserChoice) {
            var selectionChanged = self.selectedSourceType() !== "octoprint" ||
                self.selectedServerFilePath() !== path;

            if (!path) {
                clearSelectedFile(isUserChoice);
                return;
            }

            self.selectedSourceType("octoprint");
            self.selectedServerFilePath(path);
            self.selectedFileLabel(label || path);
            self.uploadedGcodeText("");
            self.uploadedFileName("");

            if (isUserChoice) {
                self.userSelectedFile = true;
            }

            if (selectionChanged) {
                resetResumeState();
            }
        }

        function setSelectedUploadedFile(fileName, fileText) {
            self.selectedSourceType("device");
            self.selectedServerFilePath("");
            self.selectedFileLabel(fileName || "no file selected");
            self.uploadedGcodeText(fileText || "");
            self.uploadedFileName(fileName || "");
            self.userSelectedFile = true;
            resetResumeState();
        }

        function clearSelectedFile(markAsUserChoice) {
            var hadSelection = !!self.selectedSourceType() ||
                !!self.selectedServerFilePath() ||
                !!self.uploadedGcodeText();

            self.selectedSourceType("");
            self.selectedServerFilePath("");
            self.selectedFileLabel("no file selected");
            self.uploadedGcodeText("");
            self.uploadedFileName("");

            if (markAsUserChoice) {
                self.userSelectedFile = true;
            }

            if (hadSelection) {
                resetResumeState();
            }
        }

        function findAvailableFileByPath(path) {
            var files = self.availableFiles();
            var index;
            for (index = 0; index < files.length; index += 1) {
                if (files[index].path === path) {
                    return files[index];
                }
            }
            return null;
        }

        function findAvailableFileByDropText(text) {
            var cleaned = $.trim(text || "");
            var files = self.availableFiles();
            var index;

            if (!cleaned) {
                return null;
            }

            cleaned = cleaned.replace(/^local\//, "");

            for (index = 0; index < files.length; index += 1) {
                if (files[index].path === cleaned || files[index].label === cleaned) {
                    return files[index];
                }
            }

            for (index = 0; index < files.length; index += 1) {
                if (files[index].label === cleaned.split("/").pop()) {
                    return files[index];
                }
            }

            return null;
        }

        function flattenFileEntries(entries, bucket) {
            var index;
            var entry;
            var path;

            for (index = 0; index < (entries || []).length; index += 1) {
                entry = entries[index];

                if (entry.type === "folder" && entry.children) {
                    flattenFileEntries(entry.children, bucket);
                    continue;
                }

                path = entry.path || OctoPrint.files.pathForEntry(entry);
                if (!path || !isSupportedGcodeName(path)) {
                    continue;
                }

                bucket.push({
                    path: path,
                    label: path
                });
            }
        }

        function updateParkFields(park) {
            if (!park) {
                return;
            }

            self.parkX(park.x != null ? park.x : "");
            self.parkY(park.y != null ? park.y : "");
            self.parkZ(park.z != null ? park.z : "");
        }

        function hasSelectedFile() {
            if (self.selectedSourceType() === "device") {
                return !!self.uploadedGcodeText();
            }

            if (self.selectedSourceType() === "octoprint") {
                return !!self.selectedServerFilePath();
            }

            return false;
        }

        function applyCurrentFileFromStatus(currentFile) {
            if (self.userSelectedFile) {
                return;
            }

            if (currentFile && currentFile.supported && currentFile.path) {
                setSelectedOctoPrintFile(currentFile.path, currentFile.name || currentFile.path, false);
                return;
            }

            if (currentFile && currentFile.name) {
                self.selectedSourceType("");
                self.selectedServerFilePath("");
                self.selectedFileLabel(currentFile.name);
                return;
            }

            clearSelectedFile(false);
        }

        function readLocalFile(file) {
            var reader;

            if (!file) {
                return;
            }

            if (!isSupportedGcodeName(file.name)) {
                notify("File Error", "Only GCODE files are supported.", "error");
                return;
            }

            reader = new FileReader();
            reader.onload = function (event) {
                setSelectedUploadedFile(file.name, event.target.result || "");
            };
            reader.onerror = function () {
                notify("File Error", "Could not read the selected file.", "error");
            };
            reader.readAsText(file);
        }

        self.loadAvailableFiles = function () {
            OctoPrint.files.listForLocation("local", true)
                .done(function (response) {
                    var files = [];
                    flattenFileEntries(response && response.files ? response.files : [], files);
                    files.sort(function (a, b) {
                        return a.label.localeCompare(b.label);
                    });
                    self.availableFiles(files);
                })
                .fail(function () {
                    self.availableFiles([]);
                });
        };

        self.loadStatus = function () {
            api("status")
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        return;
                    }

                    updateParkFields(resp.park);
                    applyCurrentFileFromStatus(resp.current_file);
                });
        };

        self.selectServerFile = function () {
            var path = self.selectedServerFilePath();
            var file = findAvailableFileByPath(path);

            if (!path) {
                clearSelectedFile(true);
                return;
            }

            setSelectedOctoPrintFile(path, file ? file.label : path, true);
        };

        self.openLocalFilePicker = function () {
            $(localFileInputSelector).trigger("click");
        };

        self.saveAssumedPosition = function () {
            var x = parseFloat(self.parkX());
            var y = parseFloat(self.parkY());
            var z = parseFloat(self.parkZ());

            if (isNaN(x) || isNaN(y) || isNaN(z)) {
                notify("Input Error", "Assumed position requires valid X, Y and Z values.", "error");
                return;
            }

            api("set_assumed_position", {
                x: x,
                y: y,
                z: z
            })
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        notify("Error", resp && resp.error ? resp.error : "Assumed position save failed", "error");
                        return;
                    }

                    updateParkFields(resp.park);
                })
                .fail(function () {
                    notify("Error", "Assumed position save failed", "error");
                });
        };

        self.validateInputs = function () {
            var measuredHeight = parseFloat(self.measuredHeight());

            if (!measuredHeight || measuredHeight <= 0) {
                notify("Input Error", "Measured height required", "error");
                return false;
            }

            if (!hasSelectedFile()) {
                notify("Input Error", "error, no file selected", "error");
                return false;
            }

            return true;
        };

        self.buildResume = function () {
            var payload;

            if (!self.validateInputs()) {
                return;
            }

            payload = {
                measured_height: parseFloat(self.measuredHeight()),
                alignment_side: self.alignmentSide()
            };

            if (self.selectedSourceType() === "device") {
                payload.uploaded_gcode_text = self.uploadedGcodeText();
                payload.uploaded_file_name = self.uploadedFileName() || self.selectedFileLabel();
            } else if (self.selectedSourceType() === "octoprint") {
                payload.file_path = self.selectedServerFilePath();
            }

            api("build_resume", payload)
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
                    }

                    if (resp.park) {
                        updateParkFields(resp.park);
                    }

                    if (resp.file && resp.file.name) {
                        self.selectedFileLabel(resp.file.name);
                    }

                    self.previewText(resp.preview ? resp.preview.join("\n") : "");
                    self.motionAcknowledged(false);
                    self.resumeBuilt(true);

                    notify("Alignment Ready", "Move printer to the selected side reference point and continue calibration.", "notice");
                })
                .fail(function () {
                    notify("Error", "API request failed", "error");
                });
        };

        self.applyPark = function () {
            api("apply_park")
                .done(function (resp) {
                    if (resp && resp.park) {
                        updateParkFields(resp.park);
                    }
                    notify("Assumed Position Set", "Toolhead reference position applied.", "success");
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
                    notify("Move Complete", "Toolhead moved to the alignment datum.", "success");
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

        self.bindFilePicker = function () {
            $(document).off("change.octogoat", localFileInputSelector);
            $(document).on("change.octogoat", localFileInputSelector, function (event) {
                var files = event.target.files || [];
                if (files.length) {
                    readLocalFile(files[0]);
                }
                event.target.value = "";
            });
        };

        self.bindDropzone = function () {
            $(document).off("dragenter.octogoat dragover.octogoat dragleave.octogoat drop.octogoat", dropzoneSelector);

            $(document).on("dragenter.octogoat dragover.octogoat", dropzoneSelector, function (event) {
                event.preventDefault();
                event.stopPropagation();
                self.isDraggingFile(true);
            });

            $(document).on("dragleave.octogoat", dropzoneSelector, function (event) {
                event.preventDefault();
                event.stopPropagation();
                self.isDraggingFile(false);
            });

            $(document).on("drop.octogoat", dropzoneSelector, function (event) {
                var nativeEvent = event.originalEvent;
                var transfer = nativeEvent ? nativeEvent.dataTransfer : null;
                var droppedFile;
                var droppedText;
                var matchedFile;

                event.preventDefault();
                event.stopPropagation();
                self.isDraggingFile(false);

                if (!transfer) {
                    return;
                }

                if (transfer.files && transfer.files.length) {
                    droppedFile = transfer.files[0];
                    readLocalFile(droppedFile);
                    return;
                }

                droppedText = transfer.getData("text/plain") || transfer.getData("text/uri-list");
                matchedFile = findAvailableFileByDropText(droppedText);

                if (matchedFile) {
                    self.selectedServerFilePath(matchedFile.path);
                    setSelectedOctoPrintFile(matchedFile.path, matchedFile.label, true);
                    return;
                }

                notify("File Error", "Only GCODE files can be dropped here.", "error");
            });
        };

        self.onBeforeBinding = function () {
            if (!document.querySelector("script[src='https://js.stripe.com/v3/pricing-table.js']")) {
                var script = document.createElement("script");
                script.src = "https://js.stripe.com/v3/pricing-table.js";
                script.async = true;
                document.body.appendChild(script);
            }
        };

        self.onAfterBinding = function () {
            self.bindFilePicker();
            self.bindDropzone();
        };

        $("#pricing-modal").on("shown.bs.modal", function () {
            var container = document.getElementById("pricing-table-container");
            if (!container || container.children.length !== 0) {
                return;
            }

            var installId = self.settingsViewModel.settings.plugins.octogoat.install_id();
            var table = document.createElement("stripe-pricing-table");

            table.setAttribute("pricing-table-id", "prctbl_1T6RDmE52GVAutfiaLKmlSue");
            table.setAttribute("publishable-key", "pk_live_51Se4ekE52GVAutfixtDzM2jB9edEZLVHIGm8EwPQ6IxZakas76Zu8xap83euJ56hnArtqEKPqS2yxwATen3yLcgn000er82jFv");
            table.setAttribute("client-reference-id", installId);

            container.appendChild(table);
        });

        self.onStartupComplete = function () {
            self.validateLicense();
            self.loadStatus();
            self.loadAvailableFiles();
        };

        self.onTabChange = function (current) {
            if (current === "#tab_plugin_octogoat") {
                self.validateLicense();
                self.loadStatus();
                self.loadAvailableFiles();
            }
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: OctoGoatViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#tab_plugin_octogoat"]
    });

});
