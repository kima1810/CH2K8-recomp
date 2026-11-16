#pragma once
#include <stdint.h>
#if defined(_WIN32)
#define CHMOD_CALL __cdecl
#define CHMOD_EXPORT __declspec(dllexport)
#else
#define CHMOD_CALL
#define CHMOD_EXPORT
#endif
#ifdef __cplusplus
extern "C" {
#endif
/* Windows x64, default packing. All APIs return a ChmodStatus. No owned host
   memory crosses the boundary. Native modules remain unsandboxed. */
typedef int32_t ChmodStatus;
enum { CHMOD_OK=0, CHMOD_E_ARGUMENT=-1, CHMOD_E_VERSION=-2,
 CHMOD_E_CAPABILITY=-3, CHMOD_E_CONFLICT=-4, CHMOD_E_LIFETIME=-5,
 CHMOD_E_CALLBACK=-6, CHMOD_E_RANGE=-7, CHMOD_E_PHASE=-8, CHMOD_E_LIMIT=-9 };
enum { CHMOD_ABI_V2=2, CHMOD_HOOK_WEIGHT_READ=1, CHMOD_HOOK_WEIGHT_WRITE=2,
 CHMOD_HOOK_RUNTIME_READY=3, CHMOD_HOOK_RUNTIME_STOPPING=4,
 CHMOD_HOOK_BUTTON_STYLE=5 };
enum { CHMOD_BUTTON_STYLE_QUERY=0, CHMOD_BUTTON_STYLE_TOGGLE=1,
 CHMOD_BUTTONS_XBOX=0, CHMOD_BUTTONS_PLAYSTATION=1 };
/* Native Options/Presentation adapter. No game objects escape this call.
   Args are immutable; after-transform may return only 0 or 1. */
typedef struct ChmodButtonStyleArgs { uint32_t action, current_style; } ChmodButtonStyleArgs;
typedef struct ChmodButtonStyleResult { uint32_t style; } ChmodButtonStyleResult;
enum { CHMOD_BEFORE=1, CHMOD_AFTER=2, CHMOD_REPLACE=3 };
enum { CHMOD_OBSERVE=0, CHMOD_TRANSFORM=1, CHMOD_REPLACEMENT=2 };
enum { CHMOD_OP_BEFORE=1, CHMOD_OP_AFTER=2, CHMOD_OP_REPLACE=4,
 CHMOD_OP_ARGUMENTS=8, CHMOD_OP_RESULT=16, CHMOD_OP_ORIGINAL=32 };
typedef uint64_t ChmodRegistration;
typedef uint64_t ChmodPlayer; /* Callback-scoped token, NOT an address/index. */
typedef struct ChmodWeightReadArgs { ChmodPlayer player; } ChmodWeightReadArgs;
typedef struct ChmodWeightReadResult { uint32_t pounds; } ChmodWeightReadResult;
typedef struct ChmodWeightWriteArgs { ChmodPlayer player; uint32_t pounds; uint32_t reserved_zero; } ChmodWeightWriteArgs;
typedef struct ChmodHookInfo {
 uint32_t size, id, version, operations, arguments_size, result_size;
 const char* name; const char* contract; /* Host-owned static UTF-8 until exit. */
} ChmodHookInfo;
typedef struct ChmodCall {
 uint32_t size, hook, phase, reserved_zero;
 uint64_t invocation; /* Borrowed, same thread, current callback only. */
 void* arguments; void* result;
 uint32_t arguments_size, result_size;
} ChmodCall;
typedef ChmodStatus (CHMOD_CALL *ChmodCallback)(void* user, ChmodCall* call);
typedef struct ChmodRegistrationSpec {
 uint32_t size, hook, hook_version, phase, mode;
 int32_t order; /* -10000..10000; within launcher/dependency module order. */
 ChmodCallback callback; void* user;
} ChmodRegistrationSpec;
typedef struct ChmodHostV2 {
 uint32_t size, abi_version;
 uint64_t session;
 ChmodStatus (CHMOD_CALL *discover)(uint64_t session,uint32_t index,ChmodHookInfo* out);
 ChmodStatus (CHMOD_CALL *has_capability)(uint64_t session,const char* name);
 ChmodStatus (CHMOD_CALL *register_hook)(uint64_t session,const ChmodRegistrationSpec*,ChmodRegistration* out);
 ChmodStatus (CHMOD_CALL *unregister_hook)(uint64_t session,ChmodRegistration);
 ChmodStatus (CHMOD_CALL *invoke_original)(uint64_t session,uint64_t invocation);
 ChmodStatus (CHMOD_CALL *read_player_weight)(uint64_t session,ChmodPlayer,uint32_t* out);
 ChmodStatus (CHMOD_CALL *set_pending_weight)(uint64_t session,ChmodPlayer,uint32_t pounds);
 ChmodStatus (CHMOD_CALL *log)(uint64_t session,uint32_t level,const char* utf8,uint32_t length);
} ChmodHostV2;
typedef struct ChmodExtensionV2 {
 uint32_t size, abi_version;
 ChmodStatus (CHMOD_CALL *initialize)(const ChmodHostV2* host);
 void (CHMOD_CALL *shutdown)(void); /* After drain, also on failed initialization. */
} ChmodExtensionV2;
typedef const ChmodExtensionV2* (CHMOD_CALL *ChmodQueryFnV2)(uint32_t abi);
/* Export ChmodQueryExtensionV2. Do not initialize from DllMain. */
#ifdef __cplusplus
}
static_assert(sizeof(void*)==8,"CHMOD SDK requires x64");
static_assert(sizeof(ChmodButtonStyleArgs)==8 && sizeof(ChmodButtonStyleResult)==4,"CHMOD Button Style payload ABI differs");
static_assert(sizeof(ChmodWeightReadArgs)==8 && sizeof(ChmodWeightReadResult)==4 && sizeof(ChmodWeightWriteArgs)==16 && sizeof(ChmodHookInfo)==40,"CHMOD typed payload ABI differs");
static_assert(sizeof(ChmodCall)==48 && sizeof(ChmodRegistrationSpec)==40,"CHMOD ABI packing differs");
static_assert(sizeof(ChmodHostV2)==80 && sizeof(ChmodExtensionV2)==24,"CHMOD host ABI differs");
#endif
