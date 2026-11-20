#include <chmod/mod.hpp>
#include <atomic>
namespace {
const ChmodHostV2* api=nullptr;
ChmodRegistration ready=0,registration=0;
ChmodStatus CHMOD_CALL on_ready(void*,ChmodCall*){
 return chmod::Host(api).log("Neutral SDK example initialized. No gameplay tuning.");
}
ChmodStatus CHMOD_CALL on_weight(void*,ChmodCall* call){
 chmod::Host host(api);
#if CHMOD_EXAMPLE_replace
 // Replacement deliberately delegates unchanged. Host caches original invocation
 // exactly once. Returning an error before invoking it also falls back to original.
 return host.original(*call);
#elif CHMOD_EXAMPLE_transform
 auto* args=chmod::weight_write(call);
 if(!args)return CHMOD_E_ARGUMENT;
 // Identity argument transformation: readable authoring, no requested game change.
 if(args->pounds<100 || args->pounds>400)return CHMOD_OK;
 return host.pending_weight(args->player,args->pounds);
#else
 auto* args=chmod::weight_read(call);if(!args)return CHMOD_E_ARGUMENT;
 uint32_t stored=0;auto status=host.weight(args->player,stored);
 static std::atomic<bool> logged=false;
 if(status==CHMOD_OK && !logged.exchange(true))return host.log("Observed a weight getter; borrowed handle checked.");
 return status;
#endif
}
ChmodStatus CHMOD_CALL initialize(const ChmodHostV2* host){
 if(!host || host->abi_version!=2 || host->size!=sizeof(*host))return CHMOD_E_VERSION;
 api=host;chmod::Host sdk(host);
 auto status=sdk.add(CHMOD_HOOK_RUNTIME_READY,CHMOD_AFTER,CHMOD_OBSERVE,on_ready,nullptr,ready);
 if(status!=CHMOD_OK)return status;
#if CHMOD_EXAMPLE_replace
 return sdk.add(CHMOD_HOOK_WEIGHT_READ,CHMOD_REPLACE,CHMOD_REPLACEMENT,on_weight,nullptr,registration);
#elif CHMOD_EXAMPLE_transform
 return sdk.add(CHMOD_HOOK_WEIGHT_WRITE,CHMOD_BEFORE,CHMOD_TRANSFORM,on_weight,nullptr,registration);
#else
 return sdk.add(CHMOD_HOOK_WEIGHT_READ,CHMOD_AFTER,CHMOD_OBSERVE,on_weight,nullptr,registration);
#endif
}
void CHMOD_CALL shutdown(){if(api){chmod::Host host(api);host.remove(ready);host.remove(registration);}api=nullptr;}
const ChmodExtensionV2 descriptor{sizeof(ChmodExtensionV2),2,initialize,shutdown};
}
extern "C" CHMOD_EXPORT const ChmodExtensionV2* CHMOD_CALL ChmodQueryExtensionV2(uint32_t abi){return abi==2?&descriptor:nullptr;}
