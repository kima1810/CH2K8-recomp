# CHMOD implementation status

For the current folder workflow, collections and feature limits, see the
[modding guide](MODDING.md) and [recent research index](research/zmo-beta-research.md).
The entries below retain their original task-specific verification status.

Current profile: schema1, API **1.3.0**, Windows x64, supported USA Xbox XEX.
Existing DDS/cloth overlays, uniform registration/automatic roster linking,
Dummy HDD isolated profiles, launcher installation/priority/dependencies/updates
and recovery remain. Native ABI1 remains compatible.

New reusable native framework implements ordered before/after observers,
argument/result transforms, exclusive replacements, original-once invocation,
registration/lifetime checks, capability discovery, checked borrowed-player access,
logging, initialization rollback and shutdown drain. Concrete adapters: Xbox
weight getter/setter and host ready/stopping lifecycle. Other domains need research.

Public SDK is hosted with Modding Studio, mirrored at [sdk/](../sdk/README.md).
Studio source CLI attaches ABI2 DLLs; Windows packaging includes the SDK. The
installed editor received the SDK directory; its executable was not rebuilt.

Runtime, neutral example DLLs and synthetic test executables **compiled**.
No tests, DLL execution, game launch or save modifications were performed for
this task. Static Ghidra evidence was saved; it is not gameplay or performance
verification. Current ABI2 capabilities are **Researched**, implemented/compiled,
not structurally validated by tests and not In-game verified.

[API1.3 spec](formats/chmod-1.3.md) Â· [Evidence](findings/2026-11-08-extension-framework.md)
Â· [Remote acceptance](../sdk/ACCEPTANCE.md). Native DLLs remain unsandboxed;
no hot unload, arbitrary guest-memory API or existing Legacy migration is provided.

Launcher update follow-up: **Update from GitHub** downloads/verifies compatible
prebuilt Windows releases into a separate runtime directory and activates through
an atomic pointer; **Rollback update** restores the prior runtime. Assets, mods,
settings and saves remain in the original installation. No compiler is needed.
See [runtime updates](RUNTIME_UPDATES.md). Implemented/static parsing only; tests,
UI and real installation/rollback execution are pending. Existing public beta is
older than the current updater/SDK contract and is safely rejected for activation.

Button Style follow-up: a normal mixed-content `.chmod` DLL + paired conditional
DDS package is installed for remote testing. Its typed SDK hook adds the native
Options/Presentation choice and submission-fenced live D3D12 variant selection.
Runtime/DLL and synthetic test compilation passed; no tests or game were run.
Selection persists outside game saves in the isolated mod profile. New capability
and matching EXE/GPU hashes are required; old ABI1/2 mods remain compatible.
See [Button Style](../sdk/BUTTON_STYLE.md) for artwork coverage and acceptance.

Mods-view repair: native-code permission refresh now retains the selected mod;
button actions stay in the original dialog scope rather than dynamic closures.
Read-only resolution accepts the installed Button Style package with no conflicts.
PowerShell syntax parsed; UI/tests/game were not executed. Reopen the launcher
to load the source fix. [Details](findings/2026-11-08-mods-view-enabling.md).
