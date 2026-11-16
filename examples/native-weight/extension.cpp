#include "../../port/src/mod_extension_abi.h"

// User-authored example. It changes only calls to the researched weight getter,
// never player/save bytes or consumers that read the field directly.
static uint32_t CHMOD_CALL weight(const ChmodWeightReadV1* event) noexcept {
  if(!event || event->size!=sizeof(ChmodWeightReadV1) || event->hook_version!=1)return 0;
  const auto original=event->original_pounds;
  if(original<100 || original>400)return original;
  auto adjusted=original+10;
  return adjusted>400?400:adjusted;
}
extern "C" __declspec(dllexport) const ChmodExtensionV1* CHMOD_CALL
ChmodQueryExtension(uint32_t host_abi_version) noexcept {
  static const ChmodExtensionV1 api{sizeof(ChmodExtensionV1),1,0,weight};
  return host_abi_version==CHMOD_EXTENSION_ABI_V1?&api:nullptr;
}
