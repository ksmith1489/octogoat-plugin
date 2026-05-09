- [x] You have read the ["Registering a new Plugin"](https://plugins.octoprint.org/help/registering/) guide.
- [x] You want to and are able to maintain the plugin you are registering, long-term.
- [x] You understand why the plugin you are registering works.
- [x] You have read and acknowledge the [Code of Conduct](https://octoprint.org/conduct/).

#### What is the name of your plugin?

Lazarus

#### What does your plugin do?

Lazarus helps users recover failed 3D prints when the partially completed print is still attached to the bed.

The plugin generates resume G-code locally inside OctoPrint from the original G-code file, the measured print height, and the detected layer structure of that file. It also provides a guided alignment workflow so the user can safely align the printer to the real-world print position before choosing to resume.

It is designed to keep the user in control of printer movement and final resume confirmation. It does not automatically home Z into an existing print.

Optional Klipper / Moonraker support is also included through a user-provided local Moonraker address.

#### Where can we find the source code of your plugin?

https://github.com/ksmith1489/lazarus-plugin

#### Was any kind of genAI (ChatGPT, Copilot etc) involved in creating this plugin?

Yes.

ChatGPT, GitHub Copilot, and Codex were used as development assistants during development and cleanup. I understand the plugin’s architecture and behavior and I am maintaining it directly.

#### Is your plugin commercial in nature?

Yes.

Lazarus is commercial software. Installation is free, but resume generation and execution require an active subscription.

Pricing, activation, license, terms, and privacy information are available here:

https://app.lazarus3dprint.com/activate
https://app.lazarus3dprint.com/license
https://app.lazarus3dprint.com/terms
https://app.lazarus3dprint.com/privacy

#### Does your plugin rely on some cloud services?

Partially.

Resume G-code generation runs locally inside the OctoPrint plugin. The original G-code file is not uploaded to the Lazarus service for resume generation.

The plugin does use https://app.lazarus3dprint.com for activation and subscription validation.

The plugin is marked with the `cloud` attribute and includes a privacy policy link:
https://app.lazarus3dprint.com/privacy

If the license validation service is unavailable, Lazarus fails closed for resume generation and execution without causing OctoPrint itself to malfunction.

#### Further notes

This is a fresh registration under `Lazarus` after the previous `OctoGoat` submission was closed.

This resubmission addresses the review items raised on `#1435`:

- the plugin has been renamed from `OctoGoat` to `Lazarus`;
- packaging has been migrated to `pyproject.toml`;
- the promotional / watermarked hero assets were removed and the UI copy was simplified;
- unused settings, no-op startup code, and unreferenced API / frontend paths were removed;
- checkout remains outside OctoPrint, and the plugin keeps server-side permission checks, server-side license enforcement, the privacy policy link, and the software update hook;
- the source repo now includes a regression test for the resume engine.

If there are any remaining repository-specific issues with this Lazarus submission, I would appreciate a concrete list and I will address them directly.
