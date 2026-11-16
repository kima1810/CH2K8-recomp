# Consuming an existing hook

Start with `examples/minimal/extension.cpp` and the matching manifest. Export the
C descriptor; retain the host table passed to initialize. Use `chmod::Host` for
capability checks, registration, checked player access, original invocation and
logging. Return the first required registration error from initialize. Do not
initialize in DllMain, include SDK/runtime private headers, or patch native memory.

Choose hook IDs from `hooks.json` and C argument/result types from `abi.h`.
`discover` returns live runtime versions, operations, sizes, names and contracts.
Declare every required capability in BOTH the extension entry and package
capabilities. Add exclusive replacement claims only if actually registering one.
Dependencies pin package ID and exact version; authors need no native address.

ABI 2 manifest extension entry:

```json
{
  "file": "code/my_mod.dll",
  "sha256": "<actual 64 lowercase hex>",
  "abi": 2,
  "capabilities": ["hook.player.weight.read", "lifecycle.runtime.ready"],
  "replacements": ["player.weight.read"]
}
```

Keep `requires.mod_api` at `1.3.0`, supported XEX hash and recomp revision from
the template. A result transformer omits replacement claims and registers AFTER /
TRANSFORM instead. An observer registers BEFORE or AFTER / OBSERVE. A setter
argument transformer registers BEFORE / TRANSFORM with `ChmodWeightWriteArgs`.
These are real implemented routes through the same dispatcher. Read-only or
unsupported phase combinations return errors, not guessed behavior.

Build and package using README commands. The example source emits three separate
DLLs: observe logs once, transform uses a checked identity pending-write, replace
calls original unchanged. These demonstrate infrastructure; they were compiled
and packaged, not loaded or tested. No existing patch is implemented.

Studio `attach-extension --abi 2 --capability ... --replacement ...` attaches an
ABI 2 DLL to an author project using the same backend as other attachments.
The project can also contain native authored assets and roster/header pairs.
Studio export and runtime opt-in remain separate: exporting never executes DLLs.
Use a runtime with matching API 1.3 schema/inventory snapshots.

**Entirely .chmod-deliverable:** DLL callbacks using available hook signatures,
allowed argument/result operations, lifecycle logging, supported checked player
weight data, plus supported DDS/cloth/uniform/native roster content and metadata.
Adding a new combination of existing hooks needs no recomp rebuild. Native DLL
opt-in, required capabilities and save isolation still apply.

**Requires a runtime adapter and recomp rebuild:** a new game function, new typed
signature or data property, new lifecycle timing, or intercepting an inlined/raw
field consumer. A .chmod cannot invent a hook ID or turn a PPC address into an
x64 patch site. Future game/simulation/scheduling/UI domains are research targets,
not current SDK features. A new adapter may require changed codegen boundaries or
call lowering; generation must preserve original bodies and symbolic interception.

Native Presentation Button Style is available through a new capability with the
existing ABI 2 host. See [contract, build and remote acceptance](BUTTON_STYLE.md).
Its source consumer is an actual mod; in-game behavior remains unverified.
