# Lazarus: Resume Failed Prints When The Print Is Still On The Bed

Hi everyone,

I've been working on a new OctoPrint plugin called **Lazarus**.

Lazarus is for the situation where a print failed, but the printed part is still attached to the bed and worth saving.

Instead of starting over, Lazarus helps the user:

- select the original G-code file;
- enter the measured height of the saved print;
- generate resume G-code locally inside OctoPrint;
- calculate a true alignment point on the partial print;
- recover a safe printer coordinate state;
- align the nozzle and resume the print under user control.

It is designed to avoid unsafe automatic Z homing into an existing print and to keep the user in control of final movement and resume confirmation.

Lazarus also supports optional Moonraker / Klipper workflows through a user-provided local Moonraker address.

## Current status

Lazarus is installable now and is currently under review for listing in the official OctoPrint plugin repository.

Until that listing is approved, it can be installed from URL in OctoPrint's Plugin Manager:

```text
https://github.com/ksmith1489/lazarus-plugin/archive/refs/heads/main.zip
```

## Source

https://github.com/ksmith1489/lazarus-plugin

## Activation / legal info

- https://app.lazarus3dprint.com/activate
- https://app.lazarus3dprint.com/license
- https://app.lazarus3dprint.com/terms
- https://app.lazarus3dprint.com/privacy

If anyone wants to try it and share feedback, edge cases, or firmware-specific behavior, I'd genuinely appreciate it.
