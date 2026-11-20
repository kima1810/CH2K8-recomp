#include <rex/runtime.h>
#include <rex/ppc.h>
#include <rex/logging.h>
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstring>
#include <string>
#include "mod_option_menu.h"

rex::Runtime* Ch2k8ScorebugRuntime();
uint32_t Ch2k8ScorebugStyle();
REX_EXTERN(__imp__sub_84764FC8);
REX_EXTERN(__imp__sub_848635D8);
REX_EXTERN(__imp__sub_848638D0);
REX_EXTERN(__imp__sub_84D23B80);
REX_EXTERN(__imp__sub_84D2DC20);
REX_EXTERN(sub_84D36C60);
REX_EXTERN(sub_84764D38);
REX_EXTERN(sub_84764550);
REX_EXTERN(sub_847CFAB8);

namespace {
using ch2k8::mods::option_menu::read_word;
using ch2k8::mods::option_menu::write_word;
constexpr uint32_t Bindings = 0x8501ada0;
constexpr uint32_t BindingSize = 208;
constexpr uint32_t HomeScore = Bindings + 8 * BindingSize + 32;
constexpr uint32_t LabelTemplate = Bindings + 10 * BindingSize + 32;
constexpr std::array<uint32_t, 2> Teams{0x85516880, 0x855165c0}; // Away, home.
constexpr std::array<uint32_t, 2> GameTeams{0x858b6840, 0x858b67f0};
constexpr size_t FieldCount = 8;
uint32_t workspace = 0;
std::array<std::u16string, FieldCount> previous;
std::array<float, FieldCount> text_widths{};
std::array<uint32_t, FieldCount> text_fonts{};
thread_local bool drawing_logo = false;
thread_local bool drawing_arrow = false;

struct LayoutTransform {
    std::array<float, 3> x, y;
    float anchor_x, anchor_y;
};

float read_float(const uint8_t* base, uint32_t address) {
    return std::bit_cast<float>(read_word(base, address));
}

void write_float(uint8_t* base, uint32_t address, float value) {
    write_word(base, address, std::bit_cast<uint32_t>(value));
}

bool readable(rex::Runtime& runtime, uint32_t address, uint32_t size) {
    return size > 0 && address >= 0x80000000 && address < 0xf0000000 - size &&
           runtime.memory()->LookupHeap(address) &&
           runtime.memory()->LookupHeap(address + size - 1);
}

bool layout_transform(rex::Runtime& runtime, const uint8_t* base, LayoutTransform& layout) {
    const auto scene = read_word(base, 0x85a5efc0);
    if (!readable(runtime, scene, 144)) return false;
    const auto instances = read_word(base, scene + 0x40);
    const auto count = read_word(base, scene + 0x3c);
    if (count > 64 || !readable(runtime, instances, count * 144)) return false;
    uint32_t poses = 0;
    for (uint32_t i = 0; i < count; ++i) {
        const auto instance = instances + i * 144;
        if (read_word(base, instance + 68) == 0xc0d7df4c)
            poses = read_word(base, instance + 116);
    }
    if (!readable(runtime, poses, 13 * 64)) return false;
    const bool usa = Ch2k8ScorebugStyle() == 1;
    layout.anchor_x = usa ? 49.f : 91.2f;
    layout.anchor_y = usa ? -185.5f : -194.f;
    const float quarter_x = usa ? -13.f : -40.28f;
    const float quarter_y = usa ? -195.f : -182.3f;
    // Three authored marker positions recover the owner's current transform
    // without assuming that score-font scale equals scene scale.
    for (uint32_t axis = 0; axis < 3; ++axis) {
        const auto home = read_float(base, poses + 2 * 64 + 48 + axis * 4);
        const auto away = read_float(base, poses + 3 * 64 + 48 + axis * 4);
        const auto quarter = read_float(base, poses + 6 * 64 + 48 + axis * 4);
        layout.x[axis] = (home - away) / (2.f * layout.anchor_x);
        layout.y[axis] = (quarter - home - layout.x[axis] * (quarter_x - layout.anchor_x)) /
                         (quarter_y - layout.anchor_y);
        if (!std::isfinite(layout.x[axis]) || !std::isfinite(layout.y[axis])) return false;
    }
    float magnitude = 0;
    for (auto value : layout.x) magnitude += value * value;
    return magnitude > .000001f;
}

std::u16string team_name(rex::Runtime& runtime, const uint8_t* base, uint32_t team) {
    // 84C6B9E8 uses the full school label at +0. The main HUD's abbreviated
    // label at +4 remains a fallback for contexts with an empty full label.
    for (uint32_t field : {0u, 4u}) {
        const auto address = read_word(base, team + field);
        if (!readable(runtime, address, 128)) continue;
        std::u16string result;
        for (uint32_t i = 0; i < 63; ++i) {
            uint16_t value;
            std::memcpy(&value, base + address + i * 2, 2);
            value = std::byteswap(value);
            if (!value) break;
            if (value < 32) { result.clear(); break; }
            if (value >= u'a' && value <= u'z') value -= u'a' - u'A';
            result.push_back(char16_t(value));
        }
        if (!result.empty()) return result;
    }
    return {};
}

std::u16string foul_text(rex::Runtime& runtime, const uint8_t* base, uint32_t team) {
    const auto rules = read_word(base, team + 0x28);
    if (!readable(runtime, rules, 16)) return {};
    // The native foul notice 84CCF6F8 displays this same active rule counter.
    const auto count = read_word(base, rules + 8);
    if (count > 99) return {};
    const auto digits = std::to_string(count);
    return u"FOULS: " + std::u16string(digits.begin(), digits.end());
}

std::u16string timeout_text(rex::Runtime& runtime, const uint8_t* base, uint32_t team) {
    const auto rules = read_word(base, team + 0x28);
    if (!readable(runtime, rules, 16)) return {};
    // Native team statistic 72 / 848AEC08, independent of the current period.
    const auto count = read_word(base, rules + 4);
    if (count > 9) return {};
    std::u16string pips;
    for (uint32_t i = 0; i < count; ++i) {
        if (i) pips += u' ';
        pips += u'-';
    }
    return pips;
}

std::u16string bonus_text(rex::Runtime& runtime, const uint8_t* base, uint32_t opponent) {
    const auto mode = read_word(base, 0x8565cc80);
    if (mode == 7 || mode == 8) return {};
    const auto rules = read_word(base, opponent + 0x28);
    if (!readable(runtime, rules, 16)) return {};
    const auto fouls = read_word(base, rules + 8);
    if (fouls > 99) return {};
    // Match 84A0B968's ordering of the native predicates 84A0F308 / 84A0F2E0.
    // The beneficiary is the team opposite the one committing these fouls.
    if (read_word(base, rules + 12) > 9 || fouls >= read_word(base, 0x8565cdec))
        return u"DOUBLE BONUS";
    if (fouls >= read_word(base, 0x8565cde8)) return u"BONUS";
    return {};
}

void set_text(PPCContext source, uint8_t* base, uint32_t cell,
              uint32_t characters, const std::u16string& value) {
    if (read_word(base, cell)) {
        source.r3.u64 = cell;
        __imp__sub_848638D0(source, base);
        write_word(base, cell, 0);
    }
    if (value.empty()) return;
    for (size_t i = 0; i <= value.size(); ++i) {
        const auto ch = std::byteswap(uint16_t(i < value.size() ? value[i] : 0));
        std::memcpy(base + characters + i * 2, &ch, 2);
    }
    source.r3.u64 = cell;
    source.r4.u64 = characters;
    __imp__sub_848635D8(source, base);
}

void draw_field(PPCContext source, uint8_t* base, size_t index,
                const std::u16string& value, float x, float y, float scale,
                uint32_t alignment, const LayoutTransform& layout, float maximum_width = 0) {
    const auto cell = workspace + uint32_t(index) * 4;
    const bool changed = value != previous[index];
    if (changed) {
        set_text(source, base, cell, workspace + 512, value);
        if (value.empty() || read_word(base, cell)) previous[index] = value;
    }
    if (value.empty() || !read_word(base, cell)) return;
    const auto context = workspace + 64;
    std::memcpy(base + context, base + LabelTemplate, 176);
    const auto font = read_word(base, context + 0x90);
    if (maximum_width > 0 && (changed || text_fonts[index] != font)) {
        auto measure = source;
        measure.r3.u64 = context;
        sub_84764D38(measure, base);
        sub_84764550(measure, base);
        measure.r4.u64 = cell;
        sub_847CFAB8(measure, base);
        text_widths[index] = float(measure.r3.s32);
        text_fonts[index] = font;
    }
    if (maximum_width > 0 && text_widths[index] * scale > maximum_width)
        scale = maximum_width / text_widths[index];
    // Anchor to the score's current world transform, including HUD animation.
    std::array<float, 16> matrix;
    for (uint32_t i = 0; i < 16; ++i) matrix[i] = read_float(base, HomeScore + i * 4);
    for (uint32_t axis = 0; axis < 3; ++axis) {
        matrix[12 + axis] += layout.x[axis] * (x - layout.anchor_x) +
                             layout.y[axis] * (y - layout.anchor_y);
        matrix[axis] = layout.x[axis] * scale;
        matrix[4 + axis] = layout.y[axis] * scale;
    }
    for (uint32_t i = 0; i < 16; ++i) write_float(base, context + i * 4, matrix[i]);
    write_word(base, context + 0x94, read_word(base, context + 0x94) & ~0x10u);
    write_word(base, context + 0x98, alignment);
    write_word(base, context + 0x9c, 0);
    for (uint32_t at : {0x68u, 0x6cu, 0x70u}) write_float(base, context + at, 255.f);
    write_word(base, context + 0xa8, 0);
    source.r3.u64 = context;
    source.r4.u64 = cell;
    __imp__sub_84764FC8(source, base);
}
}

REX_HOOK_RAW(sub_84764FC8) {
    const auto source = ctx;
    const bool score = ctx.r3.u32 == HomeScore;
    __imp__sub_84764FC8(ctx, base);
    auto* runtime = score ? Ch2k8ScorebugRuntime() : nullptr;
    if (!runtime) return;
    LayoutTransform layout;
    if (!layout_transform(*runtime, base, layout)) return;
    if (!workspace) {
        const auto allocation = runtime->memory()->SystemHeapAlloc(1040);
        if (!allocation) return;
        workspace = (allocation + 15u) & ~15u;
        std::memset(base + workspace, 0, 1024);
        REXLOG_INFO("Scorebug live team labels, timeouts, fouls and bonus fields enabled");
    }
    for (size_t side = 0; side < Teams.size(); ++side) {
        const float direction = side ? 1.f : -1.f;
        const bool usa = Ch2k8ScorebugStyle() == 1;
        draw_field(source, base, side * 4, team_name(*runtime, base, Teams[side]),
                   direction * (usa ? 155.f : 228.f), usa ? -155.f : -168.f, .68f, side ? 2 : 1,
                   layout, usa ? 100.f : 130.f);
        draw_field(source, base, side * 4 + 1, foul_text(*runtime, base, GameTeams[side]),
                   direction * 118.f, usa ? -219.f : -197.f, .48f, side ? 1 : 2, layout);
        draw_field(source, base, side * 4 + 2, bonus_text(*runtime, base, GameTeams[1-side]),
                   direction * 118.f, usa ? -210.f : -187.f, .48f, side ? 1 : 2, layout);
        draw_field(source, base, side * 4 + 3, timeout_text(*runtime, base, GameTeams[side]),
                   direction * (usa ? 49.f : 91.2f), usa ? -202.f : -205.f, .65f, 3, layout);
    }
}

REX_HOOK_RAW(sub_84D23B80) {
    const bool previous_logo = drawing_logo;
    const bool previous_arrow = drawing_arrow;
    drawing_logo = false;
    drawing_arrow = false;
    uint32_t arrow_pose = 0;
    std::array<uint8_t, 64> saved_pose{};
    if (Ch2k8ScorebugRuntime()) {
        const auto scene = read_word(base, 0x85a5efc0);
        if (scene) {
            const auto first = read_word(base, scene + 0x40);
            const auto count = read_word(base, scene + 0x3c);
            const auto instance = ctx.r3.u32;
            if (count <= 64 && instance >= first && instance - first < count * 144 &&
                (instance - first) % 144 == 0) {
                const auto identity = read_word(base, instance + 68);
                drawing_logo = identity == 0x078620f3 || identity == 0x9e8f7149;
                if (identity == 0xa3524481) {
                    // 84A06BC0 consumes and switches this alternating-possession
                    // pointer. Native initialization writes it in 849E0C90.
                    const auto entitled = read_word(base, 0x859fda98);
                    if (entitled != GameTeams[0] && entitled != GameTeams[1]) {
                        drawing_logo = previous_logo;
                        drawing_arrow = previous_arrow;
                        ctx.r3.u64 = 0;
                        return;
                    }
                    arrow_pose = read_word(base, instance + 116) + 64;
                    if (!readable(*Ch2k8ScorebugRuntime(), arrow_pose, 64)) {
                        drawing_logo = previous_logo;
                        drawing_arrow = previous_arrow;
                        ctx.r3.u64 = 0;
                        return;
                    }
                    std::memcpy(saved_pose.data(), base + arrow_pose, saved_pose.size());
                    drawing_arrow = true;
                    const float distance = Ch2k8ScorebugStyle() == 1 ? 31.f : 66.f;
                    const float offset = entitled == GameTeams[0] ? -distance : distance;
                    const float facing = entitled == GameTeams[0] ? 1.f : -1.f;
                    for (uint32_t axis = 0; axis < 3; ++axis) {
                        const auto basis = read_float(base, arrow_pose + axis * 4);
                        const auto position = arrow_pose + (12 + axis) * 4;
                        write_float(base, position, read_float(base, position) + basis * offset);
                        write_float(base, arrow_pose + axis * 4, basis * facing);
                    }
                }
            }
        }
    }
    __imp__sub_84D23B80(ctx, base);
    if (arrow_pose) std::memcpy(base + arrow_pose, saved_pose.data(), saved_pose.size());
    drawing_logo = previous_logo;
    drawing_arrow = previous_arrow;
}

REX_HOOK_RAW(sub_84D2DC20) {
    if (!drawing_logo && !drawing_arrow) {
        __imp__sub_84D2DC20(ctx, base);
        return;
    }
    // Native material state 0x60 enables alpha testing, 0x68 selects its
    // comparison, and byte 0x4c supplies the reference. Discard transparent
    // logo texels before they can write an opaque rectangle over the panel.
    const auto material = ctx.r4.u32;
    const auto commands = ctx.r3.u32;
    const auto flags = read_word(base, material + 0x40);
    const auto reference = base[material + 0x4c];
    write_word(base, material + 0x40, (flags & ~0xf0u) | 0x18000040u);
    if (drawing_arrow) write_word(base, material + 0x40,
                                 read_word(base, material + 0x40) & ~0xf000u);
    base[material + 0x4c] = 8;
    __imp__sub_84D2DC20(ctx, base);
    // Xbox render-state values and blend enums differ from desktop D3D9.
    // Queue straight-alpha blending after the material's own state setup.
    for (const auto [state, value] : std::array<std::array<uint32_t, 2>, 3>{{
             {72, 6}, {76, 7}, {80, 0}}}) {
        auto call = ctx;
        call.r3.u64 = commands;
        call.r4.u64 = state;
        call.r5.u64 = value;
        sub_84D36C60(call, base);
    }
    write_word(base, material + 0x40, flags);
    base[material + 0x4c] = reference;
}
