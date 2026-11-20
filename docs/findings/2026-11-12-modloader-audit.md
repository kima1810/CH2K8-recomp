# Modloader audit and launcher changes

| Area | Finding and change |
| --- | --- |
| Discovery | A malformed package could stop enumeration. The Mods window now lists invalid entries with the validation error. The resolver still rejects a missing, invalid, or ambiguous selected version. |
| Activation | The dialog now checks the selected executable, native capability receipt, and renderer through the same compatibility function used by launch. Check selection shows dependency, integrity, and overlap results before cache preparation. |
| Recovery | Disable and Disable all can remove an unavailable selection even if other enabled mods still have dependency errors. Launch without mods remains in the main launcher. Launch now checks package and renderer compatibility before restoring roster activation. |
| Priority | The enabled list shows highest priority first. Version switches keep their slot, and reorder operations resolve the new selection and show overlapping replacements before launch. |
| Settings | Writes check the settings hash captured by the dialog to catch changes from another launcher. A failed write restores the last saved selection in the dialog. |
| Updates | The update buttons reflect the selected package and its declared source. A disabled version can receive an update before settings exist. Only updating the active version switches the selection, and its candidate must pass launch compatibility checks. |
| Save profiles | The window previews the profile used on the next launch. Native extensions and roster packages still use isolated profiles. The Mods window and Check selection do not apply roster changes. |

The new view adds search by name, author, or ID, a package details panel, and
scrollable status output. Click Enable to select an installed version. Use Higher
priority or Lower priority to change the order. The latest package version is
not automatically enabled on installation.

The audit covered package discovery, resolution, runtime compatibility, launch
ordering, update selection, and the existing profile and recovery entry points.
Full package validation and update download still run synchronously in this view.
Native cache preparation and game behavior require separate runtime verification.
Vulkan asset replacement and new Legacy hooks remain outside the supported set.

Remote acceptance: reopen the launcher, search for Button Style, inspect its
details, and use Check selection with Direct3D 12. Verify Enable, Disable, and
Disable all persist after reopening. Use disposable packages to check malformed
entries, missing dependencies, competing overrides, and inactive-version updates.
