#pragma once
#include "native_ram_store.h"

// Include after the generated PCH, which defines REX_STORE_U8 and the Windows
// physical alias adjustment. Keep byte widths, address calculation, and order.
inline void Ch2k8StoreVectorLeft(uint8_t *base, uint32_t ea,
                                 const PPCVRegister &source,
                                 Ch2k8RamStoreScope *ram = nullptr) {
  if (ram && ram->TryStore(base, ea, source)) return;
  if ((ea & 15) == 0) {
    REX_STORE_U8(ea + 0, source.u8[15]);
    REX_STORE_U8(ea + 1, source.u8[14]);
    REX_STORE_U8(ea + 2, source.u8[13]);
    REX_STORE_U8(ea + 3, source.u8[12]);
    REX_STORE_U8(ea + 4, source.u8[11]);
    REX_STORE_U8(ea + 5, source.u8[10]);
    REX_STORE_U8(ea + 6, source.u8[9]);
    REX_STORE_U8(ea + 7, source.u8[8]);
    REX_STORE_U8(ea + 8, source.u8[7]);
    REX_STORE_U8(ea + 9, source.u8[6]);
    REX_STORE_U8(ea + 10, source.u8[5]);
    REX_STORE_U8(ea + 11, source.u8[4]);
    REX_STORE_U8(ea + 12, source.u8[3]);
    REX_STORE_U8(ea + 13, source.u8[2]);
    REX_STORE_U8(ea + 14, source.u8[1]);
    REX_STORE_U8(ea + 15, source.u8[0]);
  } else {
    for (size_t i = 0; i < (16 - (ea & 15)); ++i)
      REX_STORE_U8(ea + i, source.u8[15 - i]);
  }
}
