# Lazarus

Lazarus helps recover failed 3D prints when the partial print is still attached to the bed.

It generates resume G-code locally inside OctoPrint from the original G-code file, the measured print height, and the detected layer structure of that file, then guides the user through safe alignment before resuming.

## Status

Lazarus is installable today and is currently under review for listing in the official OctoPrint plugin repository.

Until that listing is approved, Lazarus can be installed directly from its GitHub ZIP URL through OctoPrint's Plugin Manager.

## Install From URL

In OctoPrint:

1. Open `Settings`
2. Open `Plugin Manager`
3. Choose `Get More...`
4. Select `...from URL`
5. Paste this URL:

```text
https://github.com/ksmith1489/lazarus-plugin/archive/refs/heads/main.zip
```

6. Install and restart OctoPrint when prompted

## What Lazarus Does

Lazarus is designed for recovery cases where a print failed but the printed part is still attached to the bed.

The plugin:

- reads the original G-code file locally inside OctoPrint;
- uses the measured height of the saved print to identify the likely resume layer;
- accounts for cases such as differing initial layer heights and spiral vase mode;
- generates a new resume G-code file for inspection and execution;
- calculates a true alignment point on the partial print;
- guides the user through safe coordinate-state recovery and final nozzle alignment before resuming.

Lazarus keeps the user in control of printer movement and final resume confirmation. It does not automatically home Z into an existing print.

## Recovery Workflow

Typical use looks like this:

1. Select the original G-code file from OctoPrint storage or a local device.
2. Measure the partial print and enter the measured height.
3. Generate the resume file and inspect the preview.
4. Establish a safe coordinate state.
5. Move to the calculated alignment point.
6. Align the nozzle to the saved print.
7. Download or execute the generated resume sequence.

## Firmware Support

Lazarus supports:

- standard OctoPrint printer communication;
- Marlin-based printers;
- Klipper-based printers;
- optional Moonraker / Klipper workflows through a user-provided local Moonraker address.

Depending on printer setup and user preference, Lazarus supports multiple ways to begin recovery, including:

- safe resume homing;
- using a known assumed position;
- working from an already trustworthy coordinate state.

## Safety Approach

Lazarus is built around user-controlled recovery.

It is intended to avoid unsafe automatic motion into an existing print and to keep the operator in control while:

- re-establishing coordinate state;
- confirming the real-world alignment point;
- reviewing generated resume output;
- deciding when it is actually safe to continue.

Users remain responsible for printer supervision, nozzle condition, temperature state, and confirming that recovery is appropriate for their specific machine and print.

## Licensing And Activation

Lazarus is proprietary commercial software. Installation is free, but resume generation and execution require an active subscription.

Activation, pricing, and legal information:

- Activation: https://app.lazarus3dprint.com/activate
- License: https://app.lazarus3dprint.com/license
- Terms: https://app.lazarus3dprint.com/terms
- Privacy: https://app.lazarus3dprint.com/privacy

## Source And Support

- Source: https://github.com/ksmith1489/lazarus-plugin
- Activation site: https://app.lazarus3dprint.com
- Privacy questions: ksmith1489@protonmail.com

## Development Notes

Lazarus uses modern `pyproject.toml` packaging and follows an OctoPrint cookiecutter-style repository layout.

Regression test:

```bash
python3 -m unittest tests.test_resume_engine
```

Syntax / import sanity check:

```bash
python3 -m compileall octoprint_lazarus
```
