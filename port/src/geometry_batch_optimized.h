#pragma once
#include <rex/ppc.h>
#include "linear_address_span.h"
#include <simde/x86/sse4.1.h>

// Sources must be unmodified broadcast results of DPPS with output mask 0xF.
// Finite results have identical lanes. Nonfinite DPPS results may have different
// NaN payloads per lane on some CPUs, so retain the original operations for them.
inline void Ch2k8ReciprocalSqrt4(PPCVRegister& a, PPCVRegister& b,
                               PPCVRegister& c, PPCVRegister& d,
                               const PPCVRegister& x, const PPCVRegister& y,
                               const PPCVRegister& z, const PPCVRegister& w) {
  const auto vx=simde_mm_load_ps(x.f32), vy=simde_mm_load_ps(y.f32);
  const auto vz=simde_mm_load_ps(z.f32), vw=simde_mm_load_ps(w.f32);
  auto values=simde_mm_movelh_ps(simde_mm_unpacklo_ps(vx,vy),
                               simde_mm_unpacklo_ps(vz,vw));
  const auto exponents=simde_mm_and_si128(simde_mm_castps_si128(values),
                                         simde_mm_set1_epi32(0x7F800000));
  if(simde_mm_movemask_ps(simde_mm_castsi128_ps(simde_mm_cmpeq_epi32(
      exponents,simde_mm_set1_epi32(0x7F800000))))) [[unlikely]] {
    simde_mm_store_ps(a.f32,simde_mm_div_ps(simde_mm_set1_ps(1),simde_mm_sqrt_ps(vx)));
    simde_mm_store_ps(b.f32,simde_mm_div_ps(simde_mm_set1_ps(1),simde_mm_sqrt_ps(vy)));
    simde_mm_store_ps(c.f32,simde_mm_div_ps(simde_mm_set1_ps(1),simde_mm_sqrt_ps(vz)));
    simde_mm_store_ps(d.f32,simde_mm_div_ps(simde_mm_set1_ps(1),simde_mm_sqrt_ps(vw)));
    return;
  }
  values=simde_mm_div_ps(simde_mm_set1_ps(1),simde_mm_sqrt_ps(values));
  simde_mm_store_ps(a.f32,simde_mm_shuffle_ps(values,values,0x00));
  simde_mm_store_ps(b.f32,simde_mm_shuffle_ps(values,values,0x55));
  simde_mm_store_ps(c.f32,simde_mm_shuffle_ps(values,values,0xAA));
  simde_mm_store_ps(d.f32,simde_mm_shuffle_ps(values,values,0xFF));
}

inline void Ch2k8ReciprocalSqrt3(PPCVRegister& a, PPCVRegister& b, PPCVRegister& c,
                               const PPCVRegister& x, const PPCVRegister& y,
                               const PPCVRegister& z) {
  PPCVRegister unused;
  Ch2k8ReciprocalSqrt4(a,b,c,unused,x,y,z,z);
}
inline void Ch2k8ReciprocalSqrt2(PPCVRegister& a, PPCVRegister& b,
                               const PPCVRegister& x, const PPCVRegister& y) {
  PPCVRegister unused_a,unused_b;
  Ch2k8ReciprocalSqrt4(a,b,unused_a,unused_b,x,y,x,y);
}

bool Ch2k8SelectGeometryBatch(unsigned index);
bool Ch2k8HotProfilingEnabled();
