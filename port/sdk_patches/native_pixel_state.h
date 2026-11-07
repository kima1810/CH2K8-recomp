#pragma once
#include <cstdint>
#include <array>

namespace rex::graphics::ch2k8 {
// [CONFIRMED] Exact per-draw values, carried in the shader translation key.
// No shader hash, observed scene, or assumed game-wide state is used.
constexpr uint32_t kPixelFlagMask = 0xFu << 6;
// Three states per interpolator (off, center, centroid) need 26 rather than
// 32 bits. The recovered six key bits encode exact depth/stencil decisions.
constexpr uint32_t PackInterpolators(uint32_t mask, uint32_t centroid) {
  uint32_t value=0,place=1;
  for(unsigned i=0;i<16;++i,place*=3)
    if(mask&(1u<<i)) value+=place*((centroid&(1u<<i))?2u:1u);
  return value;
}
constexpr uint32_t InterpolatorMask(uint32_t value, bool centroid_only=false) {
  uint32_t mask=0;
  for(unsigned i=0;i<16;++i,value/=3) {
    const auto digit=value%3;
    if(centroid_only ? digit==2 : digit!=0) mask|=1u<<i;
  }
  return mask;
}
// Zero is dynamic; one is fully disabled. Enabled depth has five decision
// bits plus the early-write hint. Reserve two uncommon enabled combinations
// for dynamic fallback so all encoded values fit the existing six key bits.
constexpr uint32_t PackDepthState(uint32_t flags) {
  const auto raw=(flags>>14)&127u;
  if(!raw) return 1;
  if(!(raw&1u)) return 0;
  const auto decisions=raw>>1;
  return decisions<62u ? decisions+2u : 0u;
}
constexpr uint32_t DepthFlagMask(uint32_t depth) {return depth ? 127u<<14 : 0u;}
constexpr uint32_t DepthFlags(uint32_t depth) {
  return depth>1 ? (((depth-2u)<<1)|1u)<<14 : 0u;
}
constexpr uint32_t BlendHalf(unsigned source, unsigned op, unsigned destination) {
  return source | (op << 5) | (destination << 8);
}
// Exact reversible palette: Add/Subtract/Min/Max/RevSubtract with zero/one
// factors, plus common additive factor pairs. Controls outside the exact
// palette remain dynamic. Values match the Xenos register.
// Changing this palette or the key layout requires bumping Modification::kVersion.
constexpr std::array<uint32_t,29> kBlendHalves{
  BlendHalf(1,0,1), BlendHalf(1,1,1), BlendHalf(1,2,1), BlendHalf(1,3,1), BlendHalf(1,4,1),
  BlendHalf(1,0,0), BlendHalf(1,1,0), BlendHalf(1,2,0), BlendHalf(1,3,0), BlendHalf(1,4,0),
  BlendHalf(0,0,1), BlendHalf(0,1,1), BlendHalf(0,2,1), BlendHalf(0,3,1), BlendHalf(0,4,1),
  BlendHalf(0,0,0), BlendHalf(0,1,0), BlendHalf(0,2,0), BlendHalf(0,3,0), BlendHalf(0,4,0),
  BlendHalf(6,0,7), BlendHalf(1,0,7), BlendHalf(6,0,1), BlendHalf(4,0,0), BlendHalf(8,0,0),
  BlendHalf(0,0,4), BlendHalf(8,0,4), BlendHalf(10,0,11), BlendHalf(1,0,11)};
// Preserve 29 symmetric controls, and encode standard source-alpha RGB with
// either alpha overwrite or alpha accumulation. Other controls stay dynamic.
constexpr std::array<uint32_t,31> kBlendControls=[] {
  std::array<uint32_t,31> result{};
  for(unsigned i=0;i<kBlendHalves.size();++i) result[i]=kBlendHalves[i]|(kBlendHalves[i]<<16);
  result[29]=BlendHalf(6,0,7)|(BlendHalf(1,0,0)<<16);
  result[30]=BlendHalf(6,0,7)|(BlendHalf(1,0,7)<<16);
  return result;
}();
constexpr uint32_t BlendIndex(uint32_t control) {
  for(unsigned i=0;i<kBlendControls.size();++i) if(control==kBlendControls[i]) return i+1;
  return 0;
}
// Valid MSAA modes are 0..2. Bias the low 15-bit encoding by one so zero
// remains dynamic, recovering the high bit for an exact RT0 full-write proof.
constexpr bool FullWriteEligible(uint32_t format,uint32_t normalized_mask) {
  if((normalized_mask&15u)!=15u) return false;
  switch(format) {
    case 0: case 1: case 2: case 3: case 4: case 5: case 6: case 7:
    case 10: case 12: case 14: case 15: return true;
    default: return false;
  }
}
constexpr uint32_t PackPixelState(uint32_t samples, uint32_t flags,
    uint32_t format=0, uint32_t blend=0xFFFFFFFFu, bool full_write=false) {
  if(samples>2) return 0;
  const auto raw=samples|(((flags>>6)&15u)<<2)|((format&15u)<<6)|(BlendIndex(blend)<<10);
  return (raw+1u)|(full_write?0x8000u:0u);
}
constexpr uint32_t PixelRaw(uint32_t state) {return (state&0x7FFFu) ? (state&0x7FFFu)-1u : 0u;}
constexpr bool PixelStateEnabled(uint32_t state) {return (state&0x7FFFu)!=0;}
constexpr bool FullWrite(uint32_t state) {return PixelStateEnabled(state) && (state&0x8000u);}
constexpr uint32_t PixelFlags(uint32_t state, uint32_t depth=0) {
  return (((PixelRaw(state)>>2)&15u)<<6)|DepthFlags(depth);
}
constexpr uint32_t ColorFormat(uint32_t state) {return (PixelRaw(state)>>6)&15u;}
constexpr bool HasBlend(uint32_t state) {return ((PixelRaw(state)>>10)&31u)!=0;}
constexpr uint32_t BlendControl(uint32_t state) {
  const unsigned index=(PixelRaw(state)>>10)&31u;
  if(!index) return 0;
  return kBlendControls[index-1];
}
constexpr uint32_t SampleLog2(uint32_t state,unsigned component) {
  const auto samples=PixelRaw(state)&3u;
  return component ? unsigned(samples>=1) : unsigned(samples>=2);
}
constexpr bool CanFoldFlags(uint32_t state, uint32_t mask, uint32_t depth=0) {
  return PixelStateEnabled(state) && !(mask & ~(kPixelFlagMask|DepthFlagMask(depth)));
}
constexpr bool CanFoldSamples(uint32_t state, uint32_t swizzle) {
  return PixelStateEnabled(state) && !(swizzle & 0xAAu);
}
}  // namespace rex::graphics::ch2k8
