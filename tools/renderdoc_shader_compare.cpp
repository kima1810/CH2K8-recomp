// Controlled offline shader comparison; never injects or changes live settings.
#include "renderdoc_replay.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
REPLAY_PROGRAM_MARKER();
static void collect(const rdcarray<ActionDescription> &actions,std::vector<unsigned> &ids) {
  for(const auto &a:actions) {ids.push_back(a.eventId);collect(a.children,ids);}
}
int main(int argc,char **argv) {
  const bool vertex=argc>1 && std::string(argv[argc-1])=="--vertex";
  if(vertex)--argc;
  if(argc!=5 && argc!=6) {puts("Usage: shader_compare capture.rdc target-event candidate.dxbc output-prefix [control.dxbc] [--vertex]");return 1;}
  const auto stage=vertex?ShaderStage::Vertex:ShaderStage::Pixel;
  RENDERDOC_InitialiseReplay(GlobalEnvironment{},{});
  auto file=RENDERDOC_OpenCaptureFile();
  if(!file->OpenFile(argv[1],"rdc").OK()) return 2;
  auto opened=file->OpenCapture(ReplayOptions{});
  if(!opened.first.OK()) return 3;
  auto controller=opened.second;
  const auto target=unsigned(strtoul(argv[2],nullptr,10));
  controller->SetFrameEvent(target,true);
  const auto state=controller->GetD3D12PipelineState();
  if(!state) return 4;
  const auto &selected=vertex?state->vertexShader:state->pixelShader;
  if(!selected.reflection)return 4;
  const auto original=selected.resourceId;
  std::ifstream input(argv[3],std::ios::binary|std::ios::ate);
  if(!input) return 5;
  bytebuf bytes;bytes.resize(size_t(input.tellg()));input.seekg(0);
  input.read(reinterpret_cast<char*>(bytes.data()),bytes.size());
  auto built=controller->BuildTargetShader("main",ShaderEncoding::DXBC,bytes,{},stage);
  if(built.first==ResourceId()) {printf("Build failed: %s\n",built.second.c_str());return 6;}
  ResourceId control;
  if(argc==6) {
    std::ifstream source(argv[5],std::ios::binary|std::ios::ate);
    if(!source) return 5;
    bytebuf data;data.resize(size_t(source.tellg()));source.seekg(0);
    source.read(reinterpret_cast<char*>(data.data()),data.size());
    auto baseline=controller->BuildTargetShader("main",ShaderEncoding::DXBC,data,{},stage);
    if(baseline.first==ResourceId()) return 6;
    control=baseline.first;puts("Control shader: supplied bytecode");
  }
  auto set_control=[&]() {
    if(control==ResourceId()) controller->RemoveReplacement(original);
    else controller->ReplaceResource(original,control);
  };
  ResourceId edram;
  for(const auto &r:controller->GetResources())
    if(r.name=="EDRAM Buffer") {edram=r.resourceId;break;}
  if(edram==ResourceId()) {puts("EDRAM buffer missing");return 7;}
  std::vector<unsigned> ids;collect(controller->GetRootActions(),ids);
  std::sort(ids.begin(),ids.end());
  std::vector<unsigned> checks{ids[ids.size()/3],target,ids.back()};
  for(auto event:checks) {
    controller->RemoveReplacement(original);controller->SetFrameEvent(event,true);
    auto baseline=controller->GetBufferData(edram,0,0);
    if(control!=ResourceId()) {
      set_control();controller->SetFrameEvent(event,true);
      if(baseline!=controller->GetBufferData(edram,0,0)) {
        printf("Control differs from original EDRAM at %u\n",event);return 8;
      }
    }
    controller->ReplaceResource(original,built.first);controller->SetFrameEvent(event,true);
    auto candidate=controller->GetBufferData(edram,0,0);
    if(baseline.empty() || !std::any_of(baseline.begin(),baseline.end(),
          [](uint8_t value) {return value!=0;}) || baseline!=candidate) {
      size_t differences=0;
      for(size_t i=0;i<std::min(baseline.size(),candidate.size());++i)
        differences+=baseline[i]!=candidate[i];
      printf("EDRAM mismatch event=%u bytes=%zu/%zu differences=%zu\n",event,baseline.size(),candidate.size(),differences);
      return 8;
    }
    printf("EDRAM identical event=%u bytes=%zu\n",event,baseline.size());fflush(stdout);
  }
  GPUCounter counter=GPUCounter::EventGPUDuration;bool found=false;
  for(auto id:controller->EnumerateCounters()) {
    const auto d=controller->DescribeCounter(id);
    if(d.name=="GPUTime" && d.unit==CounterUnit::Seconds &&
       d.resultType==CompType::Float && d.resultByteWidth==8) {counter=id;found=true;break;}
  }
  if(!found) return 9;
  std::ofstream out(std::string(argv[4])+"-paired.tsv");
  out<<"trial\tvariant\tevent\tms\n";
  // Warm both pipelines, then alternate measurement order to reduce clock drift.
  for(unsigned trial=0;trial<4;++trial) for(unsigned order=0;order<2;++order) {
    const bool native=bool(order^(trial&1));
    if(native) controller->ReplaceResource(original,built.first);
    else set_control();
    const auto values=controller->FetchCounters({counter});
    if(values.empty()) return 10;
    double total=0,target_ms=0;
    for(const auto &v:values) {
      const auto ms=v.value.d*1000.0;total+=ms;if(v.eventId==target) target_ms=ms;
      if(trial) out<<trial<<'\t'<<(native?"specialized":"original")<<'\t'<<v.eventId<<'\t'<<ms<<'\n';
    }
    printf("trial=%u variant=%s total_ms=%.6f target_ms=%.6f events=%zu\n",trial,native?"specialized":"original",total,target_ms,values.size());fflush(stdout);
  }
  controller->RemoveReplacement(original);controller->FreeTargetResource(built.first);
  if(control!=ResourceId()) controller->FreeTargetResource(control);
  controller->Shutdown();file->Shutdown();RENDERDOC_ShutdownReplay();return 0;
}
