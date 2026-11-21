#include "scorebug_patch.h"
#include <chmod/abi.h>
#include <rex/runtime.h>
#include <bcrypt.h>
#include <array>
#include <atomic>
#include <filesystem>
#include <fstream>
#include <string>
#include <string_view>
#include <vector>
#include <rex/logging.h>
#include <nlohmann/json.hpp>
#include "../../port/src/mod_option_menu.h"

bool BindScorebugElements(rex::runtime::FunctionDispatcher& dispatcher);

namespace {
std::vector<void*> targets;
bool owns_patch_engine = false;
PPCFunc* original_scene = nullptr;
PPCFunc* original_options = nullptr;
PPCFunc* make_string = nullptr;
PPCFunc* copy_string = nullptr;
PPCFunc* measure_string = nullptr;
std::atomic<uint32_t> active_style{2};
std::atomic<uint32_t> selected_style{0};
constexpr uint32_t Presentation = 0x8214c288;
uint32_t menu_strings = 0;
bool attempted_menu = false;
std::filesystem::path preference;

void menu_get(PPCContext& ctx, uint8_t*) { ctx.r3.u64 = selected_style.load(); }
void menu_min(PPCContext& ctx, uint8_t*) { ctx.r3.u64 = 0; }
void menu_max(PPCContext& ctx, uint8_t*) { ctx.r3.u64 = 1; }
void menu_toggle(PPCContext& ctx, uint8_t*) {
    const auto value = selected_style.fetch_xor(1) ^ 1u;
    try {
        auto pending = preference;
        pending += ".tmp";
        {
            std::ofstream file(pending, std::ios::binary | std::ios::trunc);
            file << nlohmann::json{{"version", 1}, {"network", value}} << '\n';
            file.flush();
            if (!file) throw std::runtime_error("preference write failed");
        }
        if (!MoveFileExW(pending.c_str(), preference.c_str(),
                         MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
            throw std::runtime_error("preference replacement failed");
    } catch (const std::exception& error) {
        REXLOG_WARN("Scorebug preference could not be saved: {}", error.what());
    }
    ctx.r3.u64 = 1;
}
void menu_text(PPCContext& ctx, uint8_t* base) {
    ctx.r4.u64 = menu_strings + 4 + 4 * selected_style.load();
    ctx.r5.u64 = 0;
    copy_string(ctx, base);
}
void menu_width(PPCContext& ctx, uint8_t* base) {
    ctx.r4.u64 = 0;
    ctx.r5.u64 = 1;
    ctx.r6.u64 = menu_strings + 8;
    measure_string(ctx, base);
}

void append_menu_row(PPCContext source, uint8_t* base, rex::Runtime& runtime) {
    using namespace ch2k8::mods::option_menu;
    const auto rows = read_word(base, Presentation + item_array);
    const auto count = read_word(base, Presentation + item_count);
    if (read_word(base, Presentation + 4) != 0x846d9158 ||
        read_word(base, Presentation + 12) != 0x847dc530 ||
        (count != 24 && count != 25) || !runtime.memory()->LookupHeap(rows)) return;
    uint32_t template_row = 0;
    for (uint32_t i = 0; i < count; ++i) {
        const auto row = rows + i * item_size;
        if (read_word(base, row) == 7 && read_word(base, row + item_visibility) == 0) {
            template_row = row;
            break;
        }
    }
    if (!template_row) return;
    const auto size = (count + 1) * item_size + 128;
    const auto allocation = runtime.memory()->SystemHeapAlloc(size);
    if (!allocation) return;
    std::memset(base + allocation, 0, size);
    std::memcpy(base + allocation, base + rows, count * item_size);
    const auto added = allocation + count * item_size;
    menu_strings = added + item_size;
    uint32_t cursor = menu_strings + 16;
    uint32_t cell = menu_strings;
    for (const std::u16string_view label : {u"Scorebug", u"ESPN", u"USA Sports"}) {
        auto context = source;
        context.r3.u64 = cell;
        context.r4.u64 = cursor;
        for (const auto ch : label) {
            const auto value = std::byteswap(uint16_t(ch));
            std::memcpy(base + cursor, &value, sizeof(value));
            cursor += sizeof(value);
        }
        cursor += 2;
        make_string(context, base);
        if (!read_word(base, cell)) return;
        cell += 4;
    }
    clone_item(base, added, template_row);
    write_word(base, added + item_label, menu_strings);
    auto& dispatcher = *runtime.function_dispatcher();
    const auto toggle = allocate_callback(dispatcher, base, menu_toggle);
    set_callback(base, added, Callback::increment, toggle);
    set_callback(base, added, Callback::decrement, toggle);
    set_callback(base, added, Callback::get, allocate_callback(dispatcher, base, menu_get));
    set_callback(base, added, Callback::minimum, allocate_callback(dispatcher, base, menu_min));
    set_callback(base, added, Callback::maximum, allocate_callback(dispatcher, base, menu_max));
    set_callback(base, added, Callback::text, allocate_callback(dispatcher, base, menu_text));
    set_callback(base, added, Callback::width, allocate_callback(dispatcher, base, menu_width));
    auto* heap = runtime.memory()->LookupHeap(Presentation);
    uint32_t protection = 0;
    if (!heap || !heap->Protect(Presentation, 80,
            rex::memory::kMemoryProtectRead | rex::memory::kMemoryProtectWrite, &protection)) return;
    write_word(base, Presentation + item_array, allocation);
    write_word(base, Presentation + item_count, count + 1);
    if (!heap->Protect(Presentation, 80, protection, nullptr))
        REXLOG_WARN("Scorebug presentation table protection could not be restored");
}

void options(PPCContext& ctx, uint8_t* base) {
    auto* runtime = rex::Runtime::instance();
    const auto source = ctx;
    const auto controller = source.r3.u32;
    bool presentation = false;
    if (!attempted_menu && runtime && (source.r4.u32 == 1 || source.r4.u32 == 3) &&
        controller && controller < UINT32_MAX - 228 && runtime->memory()->LookupHeap(controller + 228)) {
        const auto depth = scorebug::read_word(base, controller + 228);
        presentation = depth < 16 &&
            scorebug::read_word(base, controller + 4 * (depth + 2)) == Presentation;
    }
    original_options(ctx, base);
    // The existing Button Style adapter gets first access to the stock table.
    // The appended row is available on the next Presentation menu open.
    if (presentation) {
        attempted_menu = true;
        try {
            append_menu_row(source, base, *runtime);
        } catch (const std::exception& error) {
            REXLOG_WARN("Scorebug Presentation row unavailable: {}", error.what());
        }
    }
}

bool matching_executable() {
    std::wstring path(32768, L'\0');
    const auto length = GetModuleFileNameW(nullptr, path.data(), DWORD(path.size()));
    if (!length || length >= path.size()) return false;
    path.resize(length);
    std::ifstream executable(std::filesystem::path{path}, std::ios::binary);
    if (!executable) return false;
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0)
        return false;
    bool valid = BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0;
    std::array<unsigned char, 65536> buffer;
    while (valid && executable) {
        executable.read(reinterpret_cast<char*>(buffer.data()), buffer.size());
        if (const auto bytes = executable.gcount())
            valid = BCryptHashData(hash, buffer.data(), ULONG(bytes), 0) >= 0;
    }
    std::array<unsigned char, 32> digest;
    valid = valid && executable.eof() && !executable.bad() &&
            BCryptFinishHash(hash, digest.data(), ULONG(digest.size()), 0) >= 0;
    if (hash) BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    if (!valid) return false;
    constexpr char digits[] = "0123456789abcdef";
    std::string hex;
    for (const auto byte : digest) {
        hex += digits[byte >> 4];
        hex += digits[byte & 15];
    }
    return hex == SCOREBUG_EXECUTABLE_SHA256;
}

void scene(PPCContext& ctx, uint8_t* base) {
    constexpr uint32_t GameData = 0x3df16510;
    constexpr uint32_t BottomBar = 0x3e691786;
    constexpr uint32_t Scene = 0xe26c9b5d;
    if (ctx.r5.u32 != GameData || ctx.r6.u32 != BottomBar || ctx.r7.u32 != Scene) {
        original_scene(ctx, base);
        return;
    }
    const auto source = ctx;
    const auto style = selected_style.load();
    ctx.r6.u64 = style ? 0x79427babu : 0x3ab5ef46u;
    original_scene(ctx, base);
    const bool loaded = ctx.r3.u32 != 0;
    if (!loaded) {
        ctx = source;
        original_scene(ctx, base);
    }
    if (static_cast<uint32_t>(source.lr) == 0x84aee40c)
        active_style.store(loaded ? style : 2);
}

void CHMOD_CALL shutdown() {
    active_style.store(2);
    for (auto* target : targets) MH_QueueDisableHook(target);
    if (!targets.empty()) MH_ApplyQueued();
    for (auto* target : targets) MH_RemoveHook(target);
    targets.clear();
    if (owns_patch_engine) MH_Uninitialize();
    owns_patch_engine = false;
}

ChmodStatus CHMOD_CALL initialize(const ChmodHostV2* host) {
    try {
        auto* runtime = rex::Runtime::instance();
        if (!runtime || !runtime->function_dispatcher() || !matching_executable())
            return CHMOD_E_VERSION;
        if (!std::filesystem::is_regular_file(runtime->game_data_root() / "scorebug-probe.ready"))
            return CHMOD_E_CAPABILITY;
        preference = runtime->user_data_root() / "chmod-scorebug-preview.json";
        try {
            if (std::filesystem::is_regular_file(preference) &&
                std::filesystem::file_size(preference) < 128) {
                nlohmann::json saved;
                std::ifstream(preference) >> saved;
                const auto value = saved.at("network").get<uint32_t>();
                if (saved.at("version") == 1 && value <= 1) selected_style = value;
            }
        } catch (...) {
            REXLOG_WARN("Scorebug preference could not be read");
        }
        wchar_t style[16]{};
        const auto length = GetEnvironmentVariableW(L"CH2K8_SCOREBUG_STYLE", style, DWORD(std::size(style)));
        if (length && length < std::size(style))
            selected_style = std::wstring_view(style, length) == L"USA Sports" ? 1u : 0u;
        targets.reserve(6);
        if (MH_Initialize() != MH_OK) return CHMOD_E_CONFLICT;
        owns_patch_engine = true;
        auto& dispatcher = *runtime->function_dispatcher();
        if (!BindScorebugElements(dispatcher) ||
            !scorebug::bind(dispatcher, 0x848635D8, make_string) ||
            !scorebug::bind(dispatcher, 0x84863460, copy_string) ||
            !scorebug::bind(dispatcher, 0x84746438, measure_string) ||
            !scorebug::hook(dispatcher, 0x84D27690, scene, original_scene) ||
            !scorebug::hook(dispatcher, 0x847DC530, options, original_options)) {
            shutdown();
            return CHMOD_E_CONFLICT;
        }
        for (auto* target : targets) {
            if (MH_QueueEnableHook(target) != MH_OK) {
                shutdown();
                return CHMOD_E_CONFLICT;
            }
        }
        if (MH_ApplyQueued() != MH_OK) {
            shutdown();
            return CHMOD_E_CONFLICT;
        }
        constexpr char message[] = "Scorebug DLL patches installed";
        host->log(host->session, 2, message, sizeof(message) - 1);
        return CHMOD_OK;
    } catch (...) {
        shutdown();
        return CHMOD_E_CALLBACK;
    }
}

const ChmodExtensionV2 extension{sizeof(ChmodExtensionV2), CHMOD_ABI_V2, initialize, shutdown};
}

bool scorebug::hook(rex::runtime::FunctionDispatcher& dispatcher, uint32_t address,
                    PPCFunc* replacement, PPCFunc*& original) {
    auto* target = reinterpret_cast<void*>(dispatcher.GetFunction(address));
    MEMORY_BASIC_INFORMATION region{};
    if (!target || !VirtualQuery(target, &region, sizeof(region)) ||
        region.AllocationBase != GetModuleHandleW(nullptr) ||
        region.Protect != PAGE_EXECUTE_READ) return false;
    void* trampoline = nullptr;
    if (MH_CreateHook(target, reinterpret_cast<void*>(replacement), &trampoline) != MH_OK)
        return false;
    targets.push_back(target);
    original = reinterpret_cast<PPCFunc*>(trampoline);
    return true;
}

rex::Runtime* Ch2k8ScorebugRuntime() {
    return active_style.load() < 2 ? rex::Runtime::instance() : nullptr;
}

uint32_t Ch2k8ScorebugStyle() { return active_style.load(); }

extern "C" CHMOD_EXPORT const ChmodExtensionV2* CHMOD_CALL ChmodQueryExtensionV2(uint32_t abi) {
    return abi == CHMOD_ABI_V2 ? &extension : nullptr;
}
