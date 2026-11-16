#pragma once
#include <stdint.h>

// Windows x64 C ABI, version 1. Unsandboxed native code; explicit player opt-in.
// No ReXGlue/PPCContext layout is exposed to a package.
#if defined(_WIN32)
#define CHMOD_CALL __cdecl
#else
#define CHMOD_CALL
#endif
#ifdef __cplusplus
extern "C" {
#endif
enum { CHMOD_EXTENSION_ABI_V1 = 1, CHMOD_WEIGHT_READ_V1 = 1 };
typedef struct ChmodWeightReadV1 {
  uint32_t size;
  uint32_t hook_version;
  uint32_t player_guest_anchor; // opaque guest address, not a native pointer
  uint32_t original_pounds;
} ChmodWeightReadV1;
typedef uint32_t (CHMOD_CALL *ChmodReadWeightFnV1)(const ChmodWeightReadV1*);
typedef struct ChmodExtensionV1 {
  uint32_t size;
  uint32_t abi_version;
  uint64_t reserved_zero;
  ChmodReadWeightFnV1 player_weight_read;
} ChmodExtensionV1;
typedef const ChmodExtensionV1* (CHMOD_CALL *ChmodQueryFnV1)(uint32_t host_abi_version);
// Export exactly: const ChmodExtensionV1* CHMOD_CALL ChmodQueryExtension(uint32_t).
// Callback must be thread-safe, synchronous and noexcept; context is borrowed
// until return. Only values 100..400 are accepted; other values retain original.
// The host changes only the getter return. Guest consumers may persist derived
// behavior; the launcher therefore isolates native-code save profiles too.
#ifdef __cplusplus
}
static_assert(sizeof(ChmodWeightReadV1)==16,"CHMOD v1 context ABI differs");
static_assert(sizeof(ChmodExtensionV1)==24,"CHMOD native extensions require Windows x64 layout");
#endif
