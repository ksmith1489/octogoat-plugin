$(function () {

    function OctoGoatViewModel(parameters) {
        var self = this;
        var localFileInputSelector = "#octogoat-local-file-input";
        var dropzoneSelector = "#tab_plugin_octogoat .octogoat-file-dropzone";

        self.settingsViewModel = parameters[0];

        self.licenseValid = ko.observable(false);
        self.measuredHeight = ko.observable("");
        self.alignmentSide = ko.observable("left");
        self.controlMode = ko.observable("octoprint");
        self.moonrakerMode = ko.observable(false);
        self.moonrakerModeLabel = ko.computed(function () {
            return self.moonrakerMode() ? "ON" : "OFF";
        });

        self.resumeBuilt = ko.observable(false);
        self.resumeZ = ko.observable("");
        self.datumX = ko.observable("");
        self.datumY = ko.observable("");
        self.datumZ = ko.observable("");
        self.parkX = ko.observable("");
        self.parkY = ko.observable("");
        self.parkZ = ko.observable("");
        self.previewText = ko.observable("");
        self.resumeFileName = ko.observable("");
        self.motionAcknowledged = ko.observable(false);
        self.buildInProgress = ko.observable(false);
        self.safeStartApplied = ko.observable(false);
        self.attestCurrentCoordinates = ko.observable(false);
        self.useAssumedPositionCoordinates = ko.observable(false);
        self.safeResumeHomingStatus = ko.observable("");

        self.availableFiles = ko.observableArray([]);
        self.selectedServerFilePath = ko.observable("");
        self.selectedFileLabel = ko.observable("no file selected");
        self.selectedSourceType = ko.observable("");
        self.uploadedGcodeText = ko.observable("");
        self.uploadedFileName = ko.observable("");
        self.isDraggingFile = ko.observable(false);

        self.userSelectedFile = false;
        self.uploadedFileObject = null;
        self.uploadedServerFilePath = "";

        self.canResume = ko.computed(function () {
            return self.resumeBuilt() && self.motionAcknowledged() && self.safeStartApplied();
        });

        self.canDownloadResume = ko.computed(function () {
            return self.resumeBuilt() && !!self.resumeFileName();
        });

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

        function getApiBaseUrl() {
            return window.API_BASEURL || ((window.BASEURL || "/") + "api/");
        }

        function getFilesApiUrl() {
            return getApiBaseUrl() + "files/local?recursive=true";
        }

        function getResumeDownloadUrl() {
            return getApiBaseUrl() + "plugin/octogoat?download_resume=1&_ts=" + Date.now();
        }

        function getRequestHeaders(method) {
            if (OctoPrint && typeof OctoPrint.getRequestHeaders === "function") {
                return OctoPrint.getRequestHeaders(method || "POST");
            }

            return {};
        }

        function getAjaxErrorMessage(xhr, fallbackText) {
            if (xhr && xhr.responseJSON && xhr.responseJSON.error) {
                return xhr.responseJSON.error;
            }

            if (xhr && xhr.responseText) {
                return xhr.responseText;
            }

            if (xhr && xhr.status === 0) {
                return fallbackText + " The connection was reset before OctoPrint replied.";
            }

            return fallbackText;
        }

        function updateControlMode(mode) {
            var normalized = mode === "moonraker" ? "moonraker" : "octoprint";
            self.controlMode(normalized);
            self.moonrakerMode(normalized === "moonraker");
        }

        function resetResumeState() {
            self.resumeBuilt(false);
            self.resumeZ("");
            self.datumX("");
            self.datumY("");
            self.datumZ("");
            self.previewText("");
            self.resumeFileName("");
            self.buildInProgress(false);
            self.attestCurrentCoordinates(false);
            self.useAssumedPositionCoordinates(false);
            self.safeResumeHomingStatus("");
            self.motionAcknowledged(false);
            self.safeStartApplied(false);
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
            self.uploadedFileObject = null;
            self.uploadedServerFilePath = "";

            if (isUserChoice) {
                self.userSelectedFile = true;
            }

            if (selectionChanged) {
                resetResumeState();
            }
        }

        function setSelectedUploadedFile(file) {
            self.selectedSourceType("device");
            self.selectedServerFilePath("");
            self.selectedFileLabel(file && file.name ? file.name : "no file selected");
            self.uploadedGcodeText("");
            self.uploadedFileName(file && file.name ? file.name : "");
            self.uploadedFileObject = file || null;
            self.uploadedServerFilePath = "";
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
            self.uploadedFileObject = null;
            self.uploadedServerFilePath = "";

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

        function flattenFileEntries(entries, bucket, parentPath) {
            var index;
            var entry;
            var path;

            for (index = 0; index < (entries || []).length; index += 1) {
                entry = entries[index];
                path = entry.path || (parentPath ? parentPath + "/" + entry.name : entry.name);

                if (entry.type === "folder" && entry.children) {
                    flattenFileEntries(entry.children, bucket, path);
                    continue;
                }

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
                return !!self.uploadedFileObject;
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
            if (!file) {
                return;
            }

            if (!isSupportedGcodeName(file.name)) {
                notify("File Error", "Only GCODE files are supported.", "error");
                return;
            }

            setSelectedUploadedFile(file);
        }

        function extractUploadedLocalPath(response, fallbackName) {
            if (response && response.files && response.files.local) {
                if (response.files.local.path) {
                    return response.files.local.path;
                }

                if (response.files.local.name) {
                    return response.files.local.name;
                }
            }

            if (response && response.path) {
                return response.path;
            }

            if (response && response.name) {
                return response.name;
            }

            return fallbackName || "";
        }

        function uploadSelectedDeviceFile() {
            var deferred = $.Deferred();
            var file = self.uploadedFileObject;
            var request;
            var formData;

            if (!file) {
                deferred.reject({
                    responseJSON: {
                        error: "error, no file selected"
                    }
                });
                return deferred.promise();
            }

            if (self.uploadedServerFilePath) {
                deferred.resolve({
                    path: self.uploadedServerFilePath
                });
                return deferred.promise();
            }

            if (OctoPrint.files && typeof OctoPrint.files.upload === "function") {
                request = OctoPrint.files.upload("local", file);
            } else {
                formData = new FormData();
                formData.append("file", file, file.name);
                request = $.ajax({
                    url: getApiBaseUrl() + "files/local",
                    type: "POST",
                    data: formData,
                    processData: false,
                    contentType: false,
                    headers: getRequestHeaders("POST"),
                    dataType: "json"
                });
            }

            request
                .done(function (response) {
                    var path = extractUploadedLocalPath(response, file.name);

                    if (!path) {
                        deferred.reject({
                            responseJSON: {
                                error: "Device file upload succeeded but OctoPrint did not return a file path."
                            }
                        });
                        return;
                    }

                    self.uploadedServerFilePath = path;
                    deferred.resolve({
                        path: path,
                        response: response
                    });
                })
                .fail(function (xhr) {
                    deferred.reject(xhr);
                });

            return deferred.promise();
        }

        function handleBuildResumeSuccess(resp) {
            if (!resp || !resp.ok) {
                notify("Error", resp && resp.error ? resp.error : "Resume build failed", "error");
                return;
            }

            self.resumeZ(resp.resume_z || "");
            self.attestCurrentCoordinates(false);
            self.useAssumedPositionCoordinates(false);
            self.safeResumeHomingStatus("");
            self.safeStartApplied(false);

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

            self.resumeFileName(resp.resume_file_name || "octogoat_resume.gcode");
            self.previewText(resp.preview ? resp.preview.join("\n") : "");
            self.motionAcknowledged(false);
            self.resumeBuilt(true);

            notify("Alignment Ready", "Move printer to the selected side reference point and continue calibration.", "notice");
        }

        function requestBuildResume(payload) {
            return api("build_resume", payload)
                .done(function (resp) {
                    self.buildInProgress(false);
                    handleBuildResumeSuccess(resp);
                })
                .fail(function (xhr) {
                    self.buildInProgress(false);
                    notify(
                        "Error",
                        getAjaxErrorMessage(
                            xhr,
                            "Resume build request failed. If you selected a large local GCODE file, wait a few seconds and try once."
                        ),
                        "error"
                    );
                });
        }

        self.loadAvailableFiles = function () {
            var loader = null;

            if (OctoPrint.files && typeof OctoPrint.files.listForLocation === "function") {
                loader = OctoPrint.files.listForLocation("local", true);
            } else {
                loader = $.ajax({
                    url: getFilesApiUrl(),
                    type: "GET",
                    dataType: "json"
                });
            }

            loader
                .done(function (response) {
                    var files = [];
                    flattenFileEntries(response && response.files ? response.files : [], files, "");
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
            return api("status")
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        return;
                    }

                    updateControlMode(resp.control_mode);
                    updateParkFields(resp.park);
                    applyCurrentFileFromStatus(resp.current_file);
                });
        };

        self.setControlModeFromToggle = function () {
            var desiredMode = self.moonrakerMode() ? "moonraker" : "octoprint";

            api("set_control_mode", {
                control_mode: desiredMode
            })
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        notify("Error", resp && resp.error ? resp.error : "Control mode update failed", "error");
                        self.loadStatus();
                        return;
                    }

                    updateControlMode(resp.control_mode);
                    updateParkFields(resp.park);
                    self.attestCurrentCoordinates(false);
                    self.useAssumedPositionCoordinates(false);
                    self.safeStartApplied(false);
                    notify(
                        "Control Mode",
                        resp.moonraker_mode ? "Moonraker/Klipper mode enabled." : "OctoPrint mode enabled.",
                        "success"
                    );
                })
                .fail(function (xhr) {
                    notify("Error", getAjaxErrorMessage(xhr, "Control mode update failed"), "error");
                    self.loadStatus();
                });
        };

        self.testMoonraker = function () {
            api("test_moonraker")
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        notify("Moonraker Test", resp && resp.error ? resp.error : "Moonraker connection failed", "error");
                        return;
                    }

                    notify("Moonraker Connected", resp.message || "Moonraker connection succeeded.", "success");
                })
                .fail(function (xhr) {
                    notify("Moonraker Test", getAjaxErrorMessage(xhr, "Moonraker connection failed"), "error");
                });
        };

        self.openSafeResumeHomingPrompt = function () {
            self.loadStatus().always(function () {
                $("#safe-resume-homing-modal").modal("show");
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
                .fail(function (xhr) {
                    notify("Error", getAjaxErrorMessage(xhr, "Assumed position save failed"), "error");
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

            if (self.buildInProgress()) {
                return;
            }

            if (!self.validateInputs()) {
                return;
            }

            resetResumeState();
            self.buildInProgress(true);

            payload = {
                measured_height: parseFloat(self.measuredHeight()),
                alignment_side: self.alignmentSide()
            };

            if (self.selectedSourceType() === "device") {
                uploadSelectedDeviceFile()
                    .done(function (uploadInfo) {
                        payload.file_path = uploadInfo.path;
                        requestBuildResume(payload);
                    })
                    .fail(function (xhr) {
                        self.buildInProgress(false);
                        notify(
                            "Error",
                            getAjaxErrorMessage(xhr, "Device file upload failed"),
                            "error"
                        );
                    });
                return;
            }

            if (self.selectedSourceType() === "octoprint") {
                payload.file_path = self.selectedServerFilePath();
            }

            requestBuildResume(payload);
        };

        self.applySafeResumeHoming = function () {
            var measuredHeight = parseFloat(self.measuredHeight());

            if (!measuredHeight || measuredHeight <= 0) {
                notify("Input Error", "Measured height required", "error");
                return;
            }

            api("safe_resume_homing", {
                measured_height: measuredHeight
            })
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        notify("Error", resp && resp.error ? resp.error : "Safe Resume Homing failed", "error");
                        return;
                    }

                    self.attestCurrentCoordinates(false);
                    self.useAssumedPositionCoordinates(false);
                    self.safeStartApplied(true);
                    self.safeResumeHomingStatus(resp.message || "Safe Resume Homing started.");
                    $("#safe-resume-homing-modal").modal("hide");
                    notify("Safe Resume Homing", resp.message || "X/Y homing started.", "success");
                })
                .fail(function (xhr) {
                    notify("Error", getAjaxErrorMessage(xhr, "Safe Resume Homing failed"), "error");
                });
        };

        self.applyAssumedPosition = function () {
            api("apply_assumed_position")
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        notify("Error", resp && resp.error ? resp.error : "Assumed position command failed", "error");
                        self.useAssumedPositionCoordinates(false);
                        return;
                    }

                    if (resp.park) {
                        updateParkFields(resp.park);
                    }

                    self.attestCurrentCoordinates(false);
                    self.safeStartApplied(true);
                    self.safeResumeHomingStatus(resp.message || "Assumed position coordinates applied.");
                    $("#safe-resume-homing-modal").modal("hide");
                    notify("Assumed Position", resp.message || "Toolhead reference position applied.", "success");
                })
                .fail(function (xhr) {
                    self.useAssumedPositionCoordinates(false);
                    notify("Error", getAjaxErrorMessage(xhr, "Assumed position command failed"), "error");
                });
        };

        self.goToDatum = function () {
            $("#alignment-step-modal").modal("show");

            api("goto_datum", {
                x: self.datumX(),
                y: self.datumY(),
                z: self.datumZ()
            })
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        notify("Error", resp && resp.error ? resp.error : "Move failed", "error");
                        return;
                    }

                    notify("Move Complete", "Toolhead moved to the alignment datum.", "success");
                })
                .fail(function (xhr) {
                    notify("Error", getAjaxErrorMessage(xhr, "Move failed"), "error");
                });
        };

        self.resetAlignmentZ = function () {
            api("reset_alignment_z")
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        notify("Error", resp && resp.error ? resp.error : "Z reset failed", "error");
                        return;
                    }

                    notify("Z Coordinate Reset", resp.message || "Z coordinate reset to 200 mm.", "success");
                })
                .fail(function (xhr) {
                    notify("Error", getAjaxErrorMessage(xhr, "Z reset failed"), "error");
                });
        };

        self.lockDatum = function () {
            api("lock_datum", {
                x: self.datumX(),
                y: self.datumY(),
                z: self.datumZ()
            })
                .done(function (resp) {
                    if (!resp || resp.ok !== true) {
                        notify("Error", resp && resp.error ? resp.error : "Lock failed", "error");
                        return;
                    }

                    $("#alignment-step-modal").modal("hide");
                    notify("Alignment Locked", resp.message || "it is now safe to set nozzle temp", "success");
                })
                .fail(function (xhr) {
                    notify("Error", getAjaxErrorMessage(xhr, "Lock failed"), "error");
                });
        };

        self.downloadResume = function () {
            var link;

            if (!self.canDownloadResume()) {
                notify("Resume File", "Build the resume GCODE first.", "notice");
                return;
            }

            link = document.createElement("a");
            link.href = getResumeDownloadUrl();
            link.download = self.resumeFileName() || "octogoat_resume.gcode";
            link.style.display = "none";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        };

        self.resumeNow = function () {
            if (!self.safeStartApplied()) {
                notify("Safety", "Complete Safe Resume Homing, use assumed coordinates, or attest the current coordinate state before resuming.", "notice");
                return;
            }

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

                    notify("OctoGOAT", resp.message || "Resume sequence started", "success");
                })
                .fail(function (xhr) {
                    notify("Error", getAjaxErrorMessage(xhr, "Resume failed"), "error");
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

        self.attestCurrentCoordinates.subscribe(function (isAttested) {
            if (isAttested) {
                self.useAssumedPositionCoordinates(false);
                self.safeStartApplied(true);
                self.safeResumeHomingStatus("Current coordinate state attested.");
                return;
            }

            if (!self.useAssumedPositionCoordinates()) {
                self.safeStartApplied(false);
                self.safeResumeHomingStatus("");
            }
        });

        self.useAssumedPositionCoordinates.subscribe(function (useAssumedPosition) {
            if (useAssumedPosition) {
                self.applyAssumedPosition();
                return;
            }

            if (!self.attestCurrentCoordinates()) {
                self.safeStartApplied(false);
                self.safeResumeHomingStatus("");
            }
        });

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
            var installId;
            var table;

            if (!container || container.children.length !== 0) {
                return;
            }

            installId = self.settingsViewModel.settings.plugins.octogoat.install_id();
            table = document.createElement("stripe-pricing-table");

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
