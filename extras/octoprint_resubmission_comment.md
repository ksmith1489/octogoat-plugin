Opening this as a fresh registration under `Lazarus` after the previous `OctoGoat` submission was closed.

This resubmission addresses the concrete review items raised on `#1435`:

- the plugin has been renamed from `OctoGoat` to `Lazarus` to avoid `Octo` trademark concerns;
- packaging has been migrated to `pyproject.toml` and the repository layout has been aligned with the current OctoPrint cookiecutter-style scaffold without reverting to the legacy `setup.py` packaging path;
- the promotional / watermarked hero assets were removed and the UI copy was simplified;
- unused settings, no-op startup code, and unreferenced API/frontend paths were removed;
- checkout remains outside OctoPrint, and the plugin keeps server-side permission checks, server-side license enforcement, the privacy policy link, and the software update hook;
- the local source repo now includes a regression test for the resume engine.

If there are any remaining repository-specific issues with this Lazarus submission, I would appreciate a concrete list and I will address them directly.

Thank you for taking another look.
