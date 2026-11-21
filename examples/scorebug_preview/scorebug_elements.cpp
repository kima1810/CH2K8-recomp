#include <rex/runtime.h>
#include <rex/ppc.h>
#include <rex/logging.h>
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstring>
#include <optional>
#include <string>
#include "scorebug_patch.h"

rex::Runtime* Ch2k8ScorebugRuntime();
uint32_t Ch2k8ScorebugStyle();
PPCFunc* __imp__sub_84764FC8 = nullptr;
PPCFunc* __imp__sub_848635D8 = nullptr;
PPCFunc* __imp__sub_848638D0 = nullptr;
PPCFunc* __imp__sub_84D23B80 = nullptr;
PPCFunc* __imp__sub_84D2DC20 = nullptr;
PPCFunc* __imp__sub_84D44240 = nullptr;
PPCFunc* sub_84D36C60 = nullptr;
PPCFunc* sub_84764D38 = nullptr;
PPCFunc* sub_84764550 = nullptr;
PPCFunc* sub_847CFAB8 = nullptr;
PPCFunc* sub_848AEC08 = nullptr;
PPCFunc* sub_84D2DBE8 = nullptr;
PPCFunc* sub_84D5E978 = nullptr;
PPCFunc* sub_84D5EA28 = nullptr;

namespace {
using scorebug::read_word;
using scorebug::write_word;
constexpr uint32_t Bindings = 0x8501ada0;
constexpr uint32_t BindingSize = 208;
constexpr uint32_t HomeScore = Bindings + 8 * BindingSize + 32;
constexpr uint32_t LabelTemplate = Bindings + 10 * BindingSize + 32;
constexpr std::array<uint32_t, 2> Teams{0x85516880, 0x855165c0}; // Away, home.
constexpr std::array<uint32_t, 2> GameTeams{0x858b6840, 0x858b67f0};
constexpr uint32_t FieldsPerSide = 5;
constexpr uint32_t FieldCount = 2 * FieldsPerSide;
constexpr uint32_t TextCapacity = 64;
constexpr uint32_t TextStorageOffset = 256;
constexpr uint32_t BadgeMaterialOffset = TextStorageOffset + FieldCount * TextCapacity * 2;
constexpr uint32_t WorkspaceSize = BadgeMaterialOffset + 240;
uint32_t workspace = 0;
std::array<std::u16string, FieldCount> previous;
std::array<float, FieldCount> text_widths{};
std::array<uint32_t, FieldCount> text_fonts{};
thread_local bool drawing_logo = false;

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
        for (uint32_t i = 0; i < TextCapacity - 1; ++i) {
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

std::optional<uint32_t> remaining_timeouts(PPCContext source, uint8_t* base,
                                          rex::Runtime& runtime, size_t side) {
    const auto rules = read_word(base, GameTeams[side] + 0x28);
    if (!readable(runtime, rules, 16)) return std::nullopt;
    // 84A09760 decrements this counter. The timeout screen queries it
    // through 848AEC08 with zero for home and one for away.
    source.r3.u64 = side == 0;
    sub_848AEC08(source, base);
    if (source.r3.u32 > 9) return std::nullopt;
    return source.r3.u32;
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
                uint32_t alignment, const LayoutTransform& layout, float maximum_width = 0,
                float height_factor = 1.f, float color = 255.f, float width_factor = 1.f) {
    const auto cell = workspace + uint32_t(index) * 4;
    const bool changed = value != previous[index];
    if (changed) {
        // The native string references the UTF-16 source instead of copying it.
        const auto characters = workspace + TextStorageOffset + uint32_t(index) * TextCapacity * 2;
        set_text(source, base, cell, characters, value);
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
        matrix[axis] = layout.x[axis] * scale * width_factor;
        matrix[4 + axis] = layout.y[axis] * scale * height_factor;
    }
    for (uint32_t i = 0; i < 16; ++i) write_float(base, context + i * 4, matrix[i]);
    write_word(base, context + 0x94, read_word(base, context + 0x94) & ~0x10u);
    write_word(base, context + 0x98, alignment);
    write_word(base, context + 0x9c, 0);
    for (uint32_t at : {0x68u, 0x6cu, 0x70u}) write_float(base, context + at, color);
    write_word(base, context + 0xa8, 0);
    source.r3.u64 = context;
    source.r4.u64 = cell;
    __imp__sub_84764FC8(source, base);
}

void draw_possession_badge(PPCContext source, uint8_t* base, size_t field,
                           float x, float y, float direction, const LayoutTransform& layout) {
    struct Vertex {
        float x, y;
        uint32_t color;
    };
    // The reference silhouette is a rectangular tab with one shallow point.
    // The strip starts at the tip, then alternates top and bottom.
    constexpr std::array<Vertex, 5> shape{{
        { 5.0f,  0.0f, 0xffd7d7d7},
        { 3.2f,  3.5f, 0xffeeeeee},
        { 3.2f, -3.5f, 0xffc4c4c4},
        {-5.0f,  3.5f, 0xffeeeeee},
        {-5.0f, -3.5f, 0xffc4c4c4},
    }};
    constexpr uint32_t VertexStride = 24;
    constexpr uint32_t PositionColorUv = 0x85d82924;
    const auto material = workspace + BadgeMaterialOffset;
    auto draw = source;
    draw.r3.u64 = material;
    sub_84D2DBE8(draw, base);
    // Use the untextured material and transient vertex buffer used by the
    // native HUD text highlight (847D04F0).
    draw.r3.u64 = shape.size();
    draw.r4.u64 = PositionColorUv;
    draw.r5.u64 = material;
    draw.r6.u64 = 0;
    sub_84D5E978(draw, base);
    const auto vertices = draw.r3.u32;
    if (vertices) {
        for (size_t i = 0; i < shape.size(); ++i) {
            // Swap each upper/lower pair when reflecting to preserve winding.
            const size_t index = direction < 0 && i != 0 ? ((i - 1) ^ 1) + 1 : i;
            const auto& vertex = shape[index];
            const auto at = vertices + uint32_t(i) * VertexStride;
            for (uint32_t axis = 0; axis < 3; ++axis) {
                write_float(base, at + axis * 4,
                    read_float(base, HomeScore + (12 + axis) * 4) +
                    layout.x[axis] * (x - layout.anchor_x + direction * vertex.x) +
                    layout.y[axis] * (y - layout.anchor_y + vertex.y));
            }
            write_word(base, at + 12, vertex.color);
            write_word(base, at + 16, 0);
            write_word(base, at + 20, 0);
        }
    }
    draw.r3.u64 = vertices ? shape.size() : 0;
    sub_84D5EA28(draw, base);
    if (vertices)
        draw_field(source, base, field, u"P", x - direction * .7f, y + 1.4f,
                   .55f, 3, layout, 0, 1.f, 24.f);
}
}

void patch_sub_84764FC8(PPCContext& ctx, uint8_t* base) {
    const auto source = ctx;
    const bool score = ctx.r3.u32 == HomeScore;
    __imp__sub_84764FC8(ctx, base);
    auto* runtime = score ? Ch2k8ScorebugRuntime() : nullptr;
    if (!runtime) return;
    LayoutTransform layout;
    if (!layout_transform(*runtime, base, layout)) return;
    if (!workspace) {
        const auto allocation = runtime->memory()->SystemHeapAlloc(WorkspaceSize + 15);
        if (!allocation) return;
        workspace = (allocation + 15u) & ~15u;
        std::memset(base + workspace, 0, WorkspaceSize);
        REXLOG_INFO("Scorebug live team labels, timeouts, fouls and bonus fields enabled");
    }
    const bool usa = Ch2k8ScorebugStyle() == 1;
    const auto entitled = read_word(base, 0x859fda98);
    for (size_t side = 0; side < Teams.size(); ++side) {
        const auto field = side * FieldsPerSide;
        const float direction = side ? 1.f : -1.f;
        draw_field(source, base, field, team_name(*runtime, base, Teams[side]),
                   usa ? (side ? 120.f : -148.f) : direction * 224.f,
                   usa ? -169.f : -172.f, .87f, side ? 2 : 1,
                   layout, usa ? 80.f : 128.f);
        draw_field(source, base, field + 1, foul_text(*runtime, base, GameTeams[side]),
                   direction * (usa ? 118.f : 177.f), usa ? -219.f : -200.f, .67f,
                   side ? 2 : 1, layout, usa ? 53.f : 65.f);
        draw_field(source, base, field + 2, bonus_text(*runtime, base, GameTeams[1-side]),
                   direction * (usa ? 118.f : 177.f), usa ? -209.f : -190.f, .67f,
                   side ? 2 : 1, layout, usa ? 53.f : 65.f);
        if (const auto count = remaining_timeouts(source, base, *runtime, side)) {
            constexpr uint32_t RegularSlots = 6;
            const auto slots = std::max(*count, RegularSlots);
            const float spacing = usa ? 4.5f : 6.3f;
            for (uint32_t slot = 0; slot < slots; ++slot) {
                const float x = direction * ((usa ? 49.f : 91.2f) +
                    (float(slot) - float(slots - 1) / 2.f) * spacing);
                draw_field(source, base, field + 3, u"-", x, usa ? -205.f : -207.f,
                           .75f, 3, layout, 0, 2.1f, slot < *count ? 255.f : 95.f,
                           usa ? 1.55f : 2.0f);
            }
        }
        if (entitled == GameTeams[side])
            draw_possession_badge(source, base, field + 4, direction * (usa ? 21.f : 59.f),
                                  usa ? -205.f : -207.f, direction, layout);
    }
}

void patch_sub_84D23B80(PPCContext& ctx, uint8_t* base) {
    const bool previous_logo = drawing_logo;
    drawing_logo = false;
    uint32_t logo_pose = 0;
    std::array<uint8_t, 64> saved_pose{};
    if (auto* runtime = Ch2k8ScorebugRuntime()) {
        const auto scene = read_word(base, 0x85a5efc0);
        if (readable(*runtime, scene, 0x44)) {
            const auto first = read_word(base, scene + 0x40);
            const auto count = read_word(base, scene + 0x3c);
            const auto instance = ctx.r3.u32;
            if (first && count <= 64 && instance >= first && instance - first < count * 144 &&
                (instance - first) % 144 == 0) {
                const auto identity = read_word(base, instance + 68);
                drawing_logo = identity == 0x078620f3 || identity == 0x9e8f7149;
                if (identity == 0xa3524481) {
                    drawing_logo = previous_logo;
                    ctx.r3.u64 = 0;
                    return;
                }
                const auto poses = drawing_logo ? read_word(base, instance + 116) : 0;
                if (readable(*runtime, poses, 64)) {
                    logo_pose = poses;
                    std::memcpy(saved_pose.data(), base + logo_pose, saved_pose.size());
                    const bool home = identity == 0x9e8f7149;
                    const bool usa = Ch2k8ScorebugStyle() == 1;
                    const float center_x = usa ? (home ? 101.5f : -128.5f) :
                        (home ? 210.9f : -210.9f);
                    constexpr float CenterY = -189.5f;
                    constexpr float Scale = 1.25f;
                    const float inset_x = home ? -2.f : 2.f;
                    constexpr float DropY = -2.f;
                    for (uint32_t axis = 0; axis < 3; ++axis) {
                        const auto x = read_float(base, logo_pose + axis * 4);
                        const auto y = read_float(base, logo_pose + (4 + axis) * 4);
                        const auto position = logo_pose + (12 + axis) * 4;
                        write_float(base, position, read_float(base, position) +
                            x * (center_x * (1.f - Scale) + inset_x) +
                            y * (CenterY * (1.f - Scale) + DropY));
                        write_float(base, logo_pose + axis * 4, x * Scale);
                        write_float(base, logo_pose + (4 + axis) * 4, y * Scale);
                    }
                }
            }
        }
    }
    __imp__sub_84D23B80(ctx, base);
    if (logo_pose) std::memcpy(base + logo_pose, saved_pose.data(), saved_pose.size());
    drawing_logo = previous_logo;
}

namespace {
void set_logo_render_states(PPCContext source, uint8_t* base, uint32_t commands) {
    // Xbox render-state IDs and blend factors. Apply after the material
    // binds its state packet and before the caller queues the draw.
    for (const auto [state, value] : std::array<std::array<uint32_t, 2>, 8>{{
             {60, 1}, {64, 0}, {72, 6}, {76, 7}, {80, 0},
             {96, 1}, {100, 0}, {104, 4}}}) {
        auto call = source;
        call.r3.u64 = commands;
        call.r4.u64 = state;
        call.r5.u64 = value;
        sub_84D36C60(call, base);
    }
}
}

void patch_sub_84D2DC20(PPCContext& ctx, uint8_t* base) {
    const auto commands = ctx.r3.u32;
    __imp__sub_84D2DC20(ctx, base);
    if (drawing_logo) set_logo_render_states(ctx, base, commands);
}

void patch_sub_84D44240(PPCContext& ctx, uint8_t* base) {
    const auto commands = ctx.r3.u32;
    __imp__sub_84D44240(ctx, base);
    if (drawing_logo) set_logo_render_states(ctx, base, commands);
}

bool BindScorebugElements(rex::runtime::FunctionDispatcher& dispatcher) {
    using scorebug::bind;
    using scorebug::hook;
    return bind(dispatcher, 0x848635D8, __imp__sub_848635D8) &&
           bind(dispatcher, 0x848638D0, __imp__sub_848638D0) &&
           bind(dispatcher, 0x84D36C60, sub_84D36C60) &&
           bind(dispatcher, 0x84764D38, sub_84764D38) &&
           bind(dispatcher, 0x84764550, sub_84764550) &&
           bind(dispatcher, 0x847CFAB8, sub_847CFAB8) &&
           bind(dispatcher, 0x848AEC08, sub_848AEC08) &&
           bind(dispatcher, 0x84D2DBE8, sub_84D2DBE8) &&
           bind(dispatcher, 0x84D5E978, sub_84D5E978) &&
           bind(dispatcher, 0x84D5EA28, sub_84D5EA28) &&
           hook(dispatcher, 0x84764FC8, patch_sub_84764FC8, __imp__sub_84764FC8) &&
           hook(dispatcher, 0x84D23B80, patch_sub_84D23B80, __imp__sub_84D23B80) &&
           hook(dispatcher, 0x84D2DC20, patch_sub_84D2DC20, __imp__sub_84D2DC20) &&
           hook(dispatcher, 0x84D44240, patch_sub_84D44240, __imp__sub_84D44240);
}