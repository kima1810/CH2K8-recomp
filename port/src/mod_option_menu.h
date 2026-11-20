#pragma once

#include "ch2k8_pch.h"
#include <rex/system/function_dispatcher.h>
#include <bit>
#include <cstring>
#include <stdexcept>

namespace ch2k8::mods::option_menu {
// Retail USA option-item handler 847DC530. Keep this layout inside the runtime.
inline constexpr uint32_t item_array = 0x1C;
inline constexpr uint32_t item_count = 0x40;
inline constexpr uint32_t item_size = 0x5C;
inline constexpr uint32_t item_work = 0x4C;
inline constexpr uint32_t item_label = 0x04;
inline constexpr uint32_t item_visibility = 0x34;
enum class Callback : uint32_t {
  maximum = 0x0C, minimum = 0x10, get = 0x14, decrement = 0x18,
  increment = 0x1C, text = 0x20, width = 0x24,
};

inline uint32_t read_word(const uint8_t* base, uint32_t address) {
  uint32_t word;
  std::memcpy(&word, base + address, sizeof(word));
  return std::byteswap(word);
}

inline void write_word(uint8_t* base, uint32_t address, uint32_t word) {
  word = std::byteswap(word);
  std::memcpy(base + address, &word, sizeof(word));
}

inline uint32_t allocate_callback(rex::runtime::FunctionDispatcher& dispatcher,
                                  uint8_t* base, PPCFunc* callback) {
  static_assert(REX_THUNK_RESERVE_SIZE == rex::runtime::FunctionDispatcher::kThunkReserveSize);
  constexpr auto reserve_begin = REX_CODE_BASE + REX_CODE_SIZE;
  const auto address = dispatcher.AllocateThunk(callback, 0);
  if (address < reserve_begin || address >= reserve_begin + REX_THUNK_RESERVE_SIZE ||
      (address & 3) || dispatcher.GetFunction(address) != callback ||
      REX_LOOKUP_FUNC(base, address) != callback) {
    throw std::runtime_error("Option callback is missing from the entrypoint thunk reserve or dispatch table");
  }
  return address;
}

inline void set_callback(uint8_t* base, uint32_t item, Callback slot, uint32_t thunk) {
  write_word(base, item + static_cast<uint32_t>(slot), thunk);
}

inline void clone_item(uint8_t* base, uint32_t destination, uint32_t source) {
  std::memcpy(base + destination, base + source, item_work);
  std::memset(base + destination + item_work, 0, item_size - item_work);
}
}
