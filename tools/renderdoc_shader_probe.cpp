// Local shader/constant inspection. Exported game-derived data stays ignored.
#include "renderdoc_replay.h"
#include <algorithm>
#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <string>
REPLAY_PROGRAM_MARKER();
int main(int argc,char **argv) {
  if(argc!=4 && argc!=5) {puts("Usage: shader_probe capture.rdc event|shaders output-prefix [--vertex]");return 1;}
  const bool vertex=argc==5 && std::string(argv[4])=="--vertex";
  if(argc==5 && !vertex)return 1;
  const auto stage=vertex?ShaderStage::Vertex:ShaderStage::Pixel;
  RENDERDOC_InitialiseReplay(GlobalEnvironment{},{});
  auto file=RENDERDOC_OpenCaptureFile();
  if(!file->OpenFile(argv[1],"rdc").OK()) return 2;
  auto opened=file->OpenCapture(ReplayOptions{});
  if(!opened.first.OK()) return 3;
  auto controller=opened.second;
  const std::string selection=argv[2];
  if(selection=="shaders") {
    unsigned index=0;
    std::ofstream inventory(std::string(argv[3])+"-inventory.tsv");
    inventory<<"index\tname\tbytes\n";
    for(const auto &r:controller->GetResources()) {
      if(r.type!=ResourceType::Shader) continue;
      auto shader=controller->GetShader(ResourceId(),r.resourceId,{"main",stage});
      if(!shader || shader->stage!=stage || shader->rawBytes.empty()) continue;
      const auto prefix=std::string(argv[3])+"-shader"+std::to_string(index);
      std::ofstream binary(prefix+".dxbc",std::ios::binary);
      binary.write(reinterpret_cast<const char*>(shader->rawBytes.data()),shader->rawBytes.size());
      auto assembly=controller->DisassembleShader(ResourceId(),shader,"");
      std::ofstream text(prefix+".txt");text<<assembly.c_str();
      inventory<<index<<'\t'<<r.name.c_str()<<'\t'<<shader->rawBytes.size()<<'\n';
      if(++index==2048) break;
    }
    printf("%s_shaders,%u\n",vertex?"vertex":"pixel",index);
    controller->Shutdown();file->Shutdown();RENDERDOC_ShutdownReplay();return index?0:4;
  }
  controller->SetFrameEvent(unsigned(strtoul(argv[2],nullptr,10)),true);
  const auto state=controller->GetD3D12PipelineState();
  if(!state) return 4;
  const auto &selected=vertex?state->vertexShader:state->pixelShader;
  if(!selected.reflection)return 4;
  const auto reflection=selected.reflection;
  const auto &bytes=reflection->rawBytes;
  std::ofstream shader(std::string(argv[3])+(vertex?"-vs.dxbc":"-ps.dxbc"),std::ios::binary);
  shader.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());shader.close();
  auto usage=controller->GetUsage(selected.resourceId);
  printf("shader_usage_count,%zu\n",usage.size());
  for(const auto &u:usage) printf("usage,%u,%u\n",u.eventId,unsigned(u.usage));
  unsigned root=0;
  for(const auto &parameter:state->rootSignature.parameters) {
    const auto root_index=root++;
    const auto &binding=parameter.descriptor;
    if(binding.type!=DescriptorType::ConstantBuffer) continue;
    auto data=controller->GetBufferData(binding.resource,binding.byteOffset,
        std::min(uint64_t(4096),binding.byteSize));
    const auto path=std::string(argv[3])+"-root"+std::to_string(root_index)+"-cb"+std::to_string(parameter.reg)+"-space"+std::to_string(parameter.space)+".raw";
    std::ofstream out(path,std::ios::binary);
    out.write(reinterpret_cast<const char*>(data.data()),data.size());
    printf("constant,%u,%u,%u,%zu\n",root_index,parameter.reg,parameter.space,data.size());
  }
  controller->Shutdown();file->Shutdown();RENDERDOC_ShutdownReplay();return 0;
}
