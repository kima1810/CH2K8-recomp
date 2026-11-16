// Actual SDK consumer. Xbox menu structures, addresses and GPU state stay in
// the runtime adapter. Artwork is supplied separately by the package author.
#include <chmod/mod.hpp>
namespace {
ChmodRegistration registration{};
ChmodStatus CHMOD_CALL choice(void*,ChmodCall* call){
 const auto* args=chmod::button_style_args(call);
 auto* result=chmod::button_style_result(call);
 if(!args || !result || call->phase!=CHMOD_AFTER || args->action>CHMOD_BUTTON_STYLE_TOGGLE || args->current_style>1)return CHMOD_E_ARGUMENT;
 result->style=args->current_style ^ uint32_t(args->action==CHMOD_BUTTON_STYLE_TOGGLE);
 return CHMOD_OK;
}
ChmodStatus CHMOD_CALL initialize(const ChmodHostV2* api){
 if(!api || api->size!=sizeof(*api) || api->abi_version!=CHMOD_ABI_V2)return CHMOD_E_VERSION;
 chmod::Host host(api);
 if(!host.supports("hook.presentation.button_style"))return CHMOD_E_CAPABILITY;
 const auto status=host.add(CHMOD_HOOK_BUTTON_STYLE,CHMOD_AFTER,CHMOD_TRANSFORM,choice,nullptr,registration);
 if(status==CHMOD_OK)host.log("Button Style provider initialized; Options > Presentation");
 return status;
}
void CHMOD_CALL shutdown(){} // Host drains and retires registrations; no hot unload.
const ChmodExtensionV2 extension{sizeof(extension),CHMOD_ABI_V2,initialize,shutdown};
}
extern "C" CHMOD_EXPORT const ChmodExtensionV2* CHMOD_CALL ChmodQueryExtensionV2(uint32_t abi){return abi==CHMOD_ABI_V2?&extension:nullptr;}
