# Lazarus v0.1.1

Lazarus helps recover failed 3D prints when the partial print is still attached to the bed.

## Highlights

- Generates resume G-code locally inside OctoPrint from the original G-code file.
- Uses measured print height to identify the likely resume layer.
- Accounts for cases such as differing initial layer heights and spiral vase mode.
- Calculates a true alignment point to guide final physical nozzle alignment.
- Supports safe coordinate-state recovery workflows before resuming.
- Includes optional Moonraker / Klipper support through a user-provided local Moonraker address.

## Install

Install directly from OctoPrint's Plugin Manager using:

```text
https://github.com/ksmith1489/lazarus-plugin/archive/refs/heads/main.zip
```

In OctoPrint:

1. Open `Settings`
2. Open `Plugin Manager`
3. Choose `Get More...`
4. Select `...from URL`
5. Paste the Lazarus ZIP URL
6. Install and restart OctoPrint

## Notes

- Lazarus is proprietary commercial software.
- Installation is free, but resume generation and execution require an active subscription.
- Activation, license, terms, and privacy information are available at:
  - https://app.lazarus3dprint.com/activate
  - https://app.lazarus3dprint.com/license
  - https://app.lazarus3dprint.com/terms
  - https://app.lazarus3dprint.com/privacy

## Current Listing Status

Lazarus is installable now and is under review for listing in the official OctoPrint plugin repository.
