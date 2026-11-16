# Mods view enable/disable repair

## Follow-up: confirmed atomic settings-write error

The user screenshot and `mods.ui-error.log` identify a separate concrete failure
in `Write-ModJson`: `File.Replace(temp, destination, $null)` throws "The path is
not of a legal form" when replacing existing settings under Windows PowerShell.
PowerShell's string binding turns that backup argument into an empty string.
All three backend replacement call sites now pass the explicit CLR-null sentinel
`[System.Management.Automation.Language.NullString]::Value`. Atomic replacement
and stale-hash checks remain. The other two sites are roster activation/rollback
source paths; those operations were not invoked and no saves were changed.

The Mods view also restores the last successfully saved selection when a write
fails, preventing a failed enable from being treated internally as successful.
A regression for create/replace/disable, stale-hash rejection and temporary-file
cleanup is prepared in `tests/test_chmod_settings_write.py`, not executed.
Syntax/type inspection only; reopen the launcher before retrying the action.

## Earlier UI repairs

The installed Button Style package resolves successfully against the retained
Xbox installation with explicit native-code permission. The read-only production
resolver reports the expected DLL and two assets, with no conflicts. No game,
mod DLL, tests, cache preparation, or save operations were executed.

Static inspection found two UI defects in `tools/chmod_ui.ps1`:

- The native-code checkbox persists permission and refreshes the list. Refresh
  cleared its selected row, so a subsequent Enable / disable click could silently
  return without selecting a mod.
- Action buttons wrapped their handler in `GetNewClosure`, creating a dynamic
  module instead of retaining the dialog's original script scope. Backend helper
  functions and mutable view state should resolve in that original scope.

The view now preserves the selected ID/version during refresh and stores each
action scriptblock on its button. A normal event handler invokes that action in
the original scope, without capturing a reused loop variable. No-selection clicks
give an instruction. Checkbox save failures restore its previous state; action
failures display their message and append diagnostic context beside mod settings
as `mods.ui-error.log`. Native-code opt-in and package/source validation remain.

Verification: PowerShell syntax inspection and read-only package/source resolver
inspection only. UI interaction and tests were not executed, per user constraint.
This source-only launcher change requires reopening the launcher, not recompiling
the game or changing its package. Existing native-code permission was retained;
the agent did not change enabled selections or any user save.

Remote acceptance:

1. Reopen the launcher and Mods view; select Button Style.
2. Toggle native-code permission and confirm the row stays selected.
3. With permission enabled, click Enable / disable; confirm Yes/priority changes
   and persists when the view is reopened. Click again to disable and reopen.
4. Confirm each button invokes its own action (install, folder import, priority,
   update) and failures show a message rather than appearing unresponsive.
5. Confirm native-code packages still reject activation without opt-in. Preserve
   existing dependencies/conflict checks and recovery launch behavior.
