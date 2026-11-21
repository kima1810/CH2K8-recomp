#pragma once

#include <Windows.h>
#include <MinHook.h>
#include <rex/ppc.h>
#include <rex/system/function_dispatcher.h>
#include <bit>
#include <cstring>

namespace scorebug {
inline uint32_t read_word(const uint8_t* base, uint32_t address) {
    uint32_t value;
    std::memcpy(&value, base + address, sizeof(value));
    return std::byteswap(value);
}

inline void write_word(uint8_t* base, uint32_t address, uint32_t value) {
    value = std::byteswap(value);
    std::memcpy(base + address, &value, sizeof(value));
}

inline bool bind(rex::runtime::FunctionDispatcher& dispatcher, uint32_t address,
                 PPCFunc*& function) {
    function = dispatcher.GetFunction(address);
    return function != nullptr;
}

bool hook(rex::runtime::FunctionDispatcher& dispatcher, uint32_t address,
          PPCFunc* replacement, PPCFunc*& original);
}
