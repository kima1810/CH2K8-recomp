#include "geometry_batch_optimized.h"
#include <array>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <vector>

uint32_t seed=0x91E10DA5;
uint32_t Next(){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
void Original(PPCVRegister* out,const PPCVRegister* in,unsigned count=4) {
  for(unsigned i=0;i<count;++i)
    simde_mm_store_ps(out[i].f32,simde_mm_div_ps(simde_mm_set1_ps(1),
        simde_mm_sqrt_ps(simde_mm_load_ps(in[i].f32))));
}
void Batch(PPCVRegister* out,const PPCVRegister* in) {
  Ch2k8ReciprocalSqrt4(out[0],out[1],out[2],out[3],in[0],in[1],in[2],in[3]);
}
volatile uint64_t checksum;
template<bool Fast> double Measure(const std::vector<std::array<PPCVRegister,4>>& inputs) {
  uint64_t sum=0;PPCVRegister out[4]{};
  auto start=std::chrono::steady_clock::now();
  for(unsigned repeat=0;repeat<128;++repeat)for(const auto& in:inputs){
    if constexpr(Fast)Batch(out,in.data());else Original(out,in.data());
    for(auto& value:out)sum+=value.u64[0];
  }
  checksum=sum;
  return std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/(128*inputs.size());
}
int main(){
  const auto original_csr=simde_mm_getcsr();
  const uint32_t special[]={0,0x80000000,1,0x80000001,0x007FFFFF,0x00800000,
      0x3F800000,0xBF800000,0x7F7FFFFF,0xFF7FFFFF,0x7F800000,0xFF800000,
      0x7FC00000,0x7FA12345,0xFFC56789};
  unsigned checks=0;
  for(unsigned mode=0;mode<16;++mode){
    const unsigned csr=0x1F80|((mode&3)<<13)|((mode&4)?0x8000:0)|((mode&8)?0x40:0);
    for(unsigned trial=0;trial<50000;++trial){
      PPCVRegister in[4],expected[4],actual[4];
      for(unsigned i=0;i<4;++i){
        const uint32_t bits=trial<60?special[(trial+i)%15]:Next();
        for(auto& lane:in[i].u32)lane=bits;
        // DPPS may produce nonuniform NaN payloads on some CPUs. Exercise
        // that fallback explicitly, including signaling NaNs in upper lanes.
        if((bits&0x7F800000)==0x7F800000)for(auto& lane:in[i].u32)lane=0x7F800001|(Next()&0x807FFFFF);
      }
      simde_mm_setcsr(csr);Original(expected,in);const auto flags=simde_mm_getcsr();
      simde_mm_setcsr(csr);Batch(actual,in);const auto batch_flags=simde_mm_getcsr();
      if(std::memcmp(expected,actual,sizeof(actual))||flags!=batch_flags){
        printf("Mismatch mode=%u trial=%u flags=%x/%x\n",mode,trial,flags,batch_flags);return 2;
      }
      std::memcpy(actual,in,sizeof(actual));simde_mm_setcsr(csr);Batch(actual,actual);
      if(std::memcmp(expected,actual,sizeof(actual))||flags!=simde_mm_getcsr())return 3;
      for(unsigned count : {2u,3u}) {
        std::memcpy(actual,in,sizeof(actual));simde_mm_setcsr(csr);
        Original(expected,in,count);const auto partial_flags=simde_mm_getcsr();
        simde_mm_setcsr(csr);
        if(count==2)Ch2k8ReciprocalSqrt2(actual[0],actual[1],actual[0],actual[1]);
        else Ch2k8ReciprocalSqrt3(actual[0],actual[1],actual[2],actual[0],actual[1],actual[2]);
        if(std::memcmp(expected,actual,count*sizeof(PPCVRegister))||partial_flags!=simde_mm_getcsr())return 4;
        // Unused input vectors must remain untouched.
        if(std::memcmp(in+count,actual+count,(4-count)*sizeof(PPCVRegister)))return 5;
        simde_mm_setcsr(csr);Original(expected,in);
      }
      ++checks;
    }
  }
  simde_mm_setcsr(original_csr);
  printf("validated_batches,%u\ntrial,original_ns,batch_ns\n",checks);
  std::vector<std::array<PPCVRegister,4>> inputs(16384);
  for(auto& in:inputs)for(auto& v:in)for(auto& lane:v.f32)lane=1;
  for(auto& in:inputs)for(auto& v:in){float value=float(Next()%100000+1)/100000;for(auto& lane:v.f32)lane=value;}
  Measure<false>(inputs);Measure<true>(inputs);
  for(unsigned trial=0;trial<8;++trial){
    double a,b;if(trial&1){b=Measure<true>(inputs);a=Measure<false>(inputs);}
    else{a=Measure<false>(inputs);b=Measure<true>(inputs);}
    printf("%u,%.6f,%.6f\n",trial,a,b);
  }
}
