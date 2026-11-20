# Public ABI 2 contracts

Only `include/chmod/abi.h` is the C boundary. `mod.hpp` is a header-only C++ helper;
no ReXGlue, PPC contexts, guest pointers, native patch addresses or register layouts
are public. DLLs export `ChmodQueryExtensionV2(2)`, returning a static descriptor.
ABI 1 exports/manifest remain accepted. ABI 1 weight-read packages are exclusive
against all ABI 2 weight-read packages, preserving prior behavior conservatively.

## Initialization and capability negotiation

The launcher resolves exact dependencies and orders modules topologically with
stable low-to-high user priority among otherwise ready modules. One DLL per
package, up to 64 modules. The runtime preflights every module's required
capabilities/ABI/hash/PE before loading any. Each module receives its own retained
host table and session identity. `discover` enumerates hook metadata; index past
end returns RANGE. `has_capability` returns the intersection of runtime support
and the package's declaration. Missing required capabilities reject activation.

Register only during `initialize`; perform no work in DllMain. Each registration
pins hook ID and version, phase, mode, local order, callback and user pointer.
Replacement registrations also require the manifest's exclusive replacement claim.
Registration errors are returned, not silently ignored. Initialization must return
failure if a required registration fails. No gameplay dispatch is published until
all initializers succeed; earlier registrations are retired on rollback and
shutdown callbacks run in reverse module order, including the failed initializer.
Native DllMain/initialization side effects cannot be rolled back by the host.

The host table, metadata strings and descriptor remain valid until process exit.
All callback/user state must remain alive through dispatch drain and shutdown;
unregister does not authorize freeing it early. No hot reload/unload is supported.
Modules remain loaded until OS process teardown. Do not cache invocation or player
handles, payload pointers or borrowed buffers beyond the callback. Tokens are
monotonic opaque identities, not persistent player IDs and not addresses.

## Composition

For each function: all BEFORE callbacks run, then one replacement or the original,
then all AFTER callbacks run. Each phase uses module order, local `order` ascending,
then registration sequence. AFTER is forward order, not stack unwinding order.
Observers receive typed scratch views whose edits are discarded. Supported
transformations compose sequentially. Only setter BEFORE arguments and getter
AFTER results are currently mutable; other combinations return PHASE.

A replacement may supply a getter result, skip the setter write, or call
`invoke_original`. Original uses the current validated arguments and bypasses all
mod callbacks. It runs at most once per invocation; repeated requests restore the
cached original result without repeating side effects. AFTER still executes.
There is no general observer cancellation. Skipping original is allowed only by
an exclusive replacement, including the setter's explicit no-write behavior.
No method may undo effects of an original already invoked. Mutating arguments
after original invocation does not repeat or change that completed write.

A callback returning failure, throwing a C++ exception, or producing an invalid
payload is disabled. Its pending edits are discarded. Failed replacement invokes
the original if not already called; otherwise its cached original result is used.
Other callbacks continue. With no extension, adapters execute the exact original.
C++ exception handling does NOT recover access violations, stack corruption,
process termination, deadlocks or arbitrary native crashes. Recovery launch is
required after such failures. FP environment/MXCSR is preserved around callbacks.

## Handles, data, lifetime and threads

Game callbacks run synchronously on whichever guest caller thread reaches the
adapter. They can run concurrently; mods must protect their own state. Same-hook
reentrancy bypasses callbacks and executes original behavior; nested different
hooks get separate invocation scopes. Original invocation and player accessors
are valid only for the owning session's currently active callback and thread.
No blocking waits on game/UI threads, long-running work, or assumptions of a
main-thread player callback are allowed. Do not retain or cross-thread tokens.

`read_player_weight` reads the supported packed property through the original
getter on a private PPC context copy, using only the adapter's borrowed player.
It is available in read/write callbacks, returning native stored pounds (0..511).
`set_pending_weight` checks the borrowed handle and capability and changes only
an uncommitted setter BEFORE/replacement argument (100..400). It rejects observers,
AFTER and calls after original invocation. The typed setter argument may also be
transformed directly. This changes supported game data when the normal original
setter executes; no arbitrary memory read/write facility exists.

`unregister_hook` is allowed from initialize, own callbacks and shutdown. Future
snapshot dispatch skips it; callbacks already in progress may finish. User data
cannot be freed until shutdown. Registration during active dispatch is rejected.
Logging (explicit length <=4096 bytes), discovery and capability queries are
thread-safe while the module is retained. Strings/buffers passed to host logging
are copied synchronously; the caller owns them. Other host calls return statuses
listed in the ABI header. No allocated strings or buffers require cross-CRT free.

## Lifecycle and shutdown

`runtime.ready` is an AFTER/observe event at OnPostSetup after module initialization,
before the guest module is launched. It is not a game/session/roster-loaded event.
`runtime.stopping` is AFTER/observe on the host OnShutdown thread after new mod
dispatch is suppressed and in-flight mod callbacks drain. Guest execution may
still exist; it does not certify a save flush or guest shutdown. No player handles
are available. Then DLL shutdown functions run in reverse initialization order.
Mods must stop/join their own workers before shutdown returns. A callback that
never returns can prevent drain; forced termination is not safe unloading.

Code selections keep existing isolated persistent Dummy HDD profiles. Getter
results can influence data later persisted by guest consumers; setter changes
modify a real player field and may persist when the game saves. No existing
Legacy saves are copied, migrated or approved for editing. Recovery suppresses
all extension loading and restores baseline selection under existing policies.
