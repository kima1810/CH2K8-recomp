# 2026-11-02: Codegen, callback and save enumeration review

## Report and scope

The user reports a Quick Play buzzer crash and duplicate Settings/User/Legacy
entries. They report Legacy creation, save/reload, simulation and season rollover
working. This is user-reported acceptance, not a new automated gameplay run.
No crash log or missing guest address is available. No game is launched here.

## Existing corrections verified

- `fix_codegen.py` already corrects both NORMPACKED64 pack/unpack lane and half
  ordering, biased float-bit conversion and signed overflow behavior. Generated
  sites and an independent Xenia SIMD oracle are covered by native tests.
- The original table export compares **1,762/1,762** generated inline dispatches:
  **zero truncated prefixes and zero disagreements**. The two hint files retain
  37 recovered tables. The reported count of 34 is not used as an assumption
  about the exact retail XEX or the scope of other switch idioms.
- Verified descriptor/script/flag/zero-argument callback registrations already
  exist in `pointer_funcs.toml`. This does not cover every indirect target.
- Accurate Xbox blending already selects D3D12 ROV. Automatic/Native retain the
  previously user-validated bounded-transfer RTV configuration because changing
  them globally would reintroduce the measured severe menu slowdown. The exact
  EDRAM gamma-to-linear failure described in the report has not been captured
  here; a compatible ROV fallback is available without claiming an RTV fix.

## Callback coverage audit

`ghidra/ExportUnregisteredDataCallbacks.java` scans aligned big-endian words in
initialized non-executable blocks and compares code-range values with the actual
generated registry. It writes a private report, never changes the Ghidra program,
and never automatically promotes raw values to functions. No additional
Ghidra-recognized function entries were missing from this registry. The wider
raw scan yields 11,712 candidates, including floating-point data collisions and
interior code addresses. They are not 11,712 missing functions. No additional
isolated, zero-padded short tail-wrapper entries were verified in that set.
Arbitrary pointers, unrecognized bodies and computed targets remain unresolved.
The buzzer crash cannot be declared fixed without its target and a runtime retry.

## New aggregate enumeration correction

The pinned SDK enumerates the requested XUID's package root and then the common
XUID-zero root whenever the signed-in profile is nonzero. For a requested XUID
of zero these are the same physical root, so every entry is returned twice.
Repeated alternate title IDs, including the current-title sentinel plus its
concrete value, can repeat another root visit. This is a confirmed source defect
and a plausible cause of the reported UI duplicates; its actual triggering
arguments in this user's save flow were not captured.

`ContentRoots` identifies visited roots by XUID and resolved title ID. The
aggregate enumerator skips only repeated visits within that call. It preserves
the existing user/common lookup policy, separate users/titles and every distinct
package, even when display names match. It neither deletes nor rewrites saves.
`prepare_content_sdk.py` applies the narrow, exact-site patch idempotently and
rejects unexpected source layouts before writing. The standard patched SDK
preparation now includes it.

Native regression checks cover zero-XUID double visits, explicit/current-title
aliases, repeated alternate IDs and distinct users/titles. The runtime and
dual-renderer recomp are rebuilt with the correction. Source builds use the
matching VS18 toolset; the older VS2022 toolset cannot reuse those PCH files.
The repository suite passes **109 tests, one skipped**. The packed-vector native
oracle and content-root native executable both execute successfully. The patched
SDK DLL is installed and staged beside the normal launcher's preferred
`win-amd64-vulkan/ch2k8.exe`; no runtime launch or save-list acceptance is claimed.

## Limits

Duplicate physical packages already present are retained. The fix addresses
enumeration duplication and is not a migration/deduplication of save data.
User testing of the save list and buzzer transition is still required. No
blanket fatal suppression, return-value stubs or guessed function hints added.

Related primary implementation reference:
[Xenia aggregate enumeration](https://github.com/xenia-project/xenia/blob/master/src/xenia/kernel/xam/xam_content_aggregate.cc).
The local pinned SDK is the authority for the defect and patch sites above.
