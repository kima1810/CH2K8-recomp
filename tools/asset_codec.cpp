// Bounded H7A decoder for offline asset import. No game/runtime dependencies.
#include <cstddef>
#include <cstdint>
#include <cstring>
#ifdef _WIN32
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C"
#endif
EXPORT uint64_t ch2k8_fnv64(const uint8_t* input,size_t size) {
  uint64_t hash=14695981039346656037ull;
  for(size_t i=0;i<size;++i) hash=(hash^input[i])*1099511628211ull;
  return hash;
}
EXPORT int ch2k8_h7a(const uint8_t* input,size_t size,uint8_t* output,size_t length) {
  auto be=[](const uint8_t* p){return uint32_t(p[0])<<24|uint32_t(p[1])<<16|uint32_t(p[2])<<8|p[3];};
  if(size<20 || be(input)!=0x0E4837C3 || be(input+4)!=length || be(input+8)!=size) return 0;
  unsigned shift=be(input+16);
  if(!shift || shift>16) return 0;
  size_t pos=20,out=0;
  while(out<length) {
    if(pos>=size) return 0;
    unsigned flags=input[pos++];
    for(unsigned bit=0;bit<8 && out<length;++bit) {
      if(flags&(1u<<bit)) {
        if(pos+2>size) return 0;
        unsigned token=unsigned(input[pos])<<8|input[pos+1]; pos+=2;
        size_t distance=token&((1u<<shift)-1),count=(token>>shift)+3;
        if(!distance || distance>out) return 0;
        if(count>length-out) count=length-out;
        for(size_t i=0;i<count;++i) { output[out]=output[out-distance]; ++out; }
      } else {
        if(pos>=size) return 0;
        output[out++]=input[pos++];
      }
    }
  }
  return 1;
}
