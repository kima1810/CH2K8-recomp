// Off-line per-action replay timings via the public RenderDoc AMD GPUTime
// counter.
#include "renderdoc_replay.h"
#include <algorithm>
#include <cstdio>
#include <fstream>
#include <map>
#include <string>
#include <vector>
#include <windows.h>
REPLAY_PROGRAM_MARKER();
void actions(const rdcarray<ActionDescription> &list, std::ofstream &out,
             const SDFile &sd) {
  for (const auto &a : list) {
    auto name = a.GetName(sd);
    for (auto &c : name)
      if (c == '\t' || c == '\n' || c == '\r')
        c = ' ';
    out << a.eventId << '\t' << a.numIndices << '\t' << a.numInstances << '\t'
        << name.c_str() << '\n';
    actions(a.children, out, sd);
  }
}
int main(int argc, char **argv) {
  const bool diagnostics=argc==4 && std::string(argv[3])=="--diagnostics-only";
  if (argc != 3 && !diagnostics) {
    puts("Usage: renderdoc_replay <capture.rdc> <output-prefix> [--diagnostics-only]");
    return 1;
  }
  RENDERDOC_InitialiseReplay(GlobalEnvironment{}, {});
  auto file = RENDERDOC_OpenCaptureFile();
  auto result = file->OpenFile(argv[1], "rdc");
  if (!result.OK()) {
    printf("OpenFile error %u\n", unsigned(result.code));
    return 2;
  }
  puts("Opening replay");
  fflush(stdout);
  auto replay = file->OpenCapture(ReplayOptions{});
  if (!replay.first.OK()) {
    printf("Replay error %u\n", unsigned(replay.first.code));
    return 3;
  }
  auto controller = replay.second;
  auto log_file=reinterpret_cast<const char* (__cdecl*)()>(
      GetProcAddress(GetModuleHandleW(L"renderdoc.dll"),"RENDERDOC_GetLogFile"));
  if(log_file) printf("RenderDoc log: %s\n",log_file());
  auto save_log=[&]() {
    auto contents=reinterpret_cast<void (__cdecl*)(uint64_t,rdcstr&)>(
        GetProcAddress(GetModuleHandleW(L"renderdoc.dll"),"RENDERDOC_GetLogFileContents"));
    if(contents) {
      rdcstr data;contents(0,data);
      std::ofstream out(std::string(argv[2])+"-renderdoc.log");out<<data.c_str();
    }
  };
  if(diagnostics) {
    for(auto id:controller->EnumerateCounters()) {
      const auto d=controller->DescribeCounter(id);
      printf("Counter %u %s unit=%u type=%u bytes=%u\n",unsigned(id),d.name.c_str(),
             unsigned(d.unit),unsigned(d.resultType),d.resultByteWidth);
    }
    save_log();controller->Shutdown();file->Shutdown();RENDERDOC_ShutdownReplay();return 0;
  }
  std::ofstream events(std::string(argv[2]) + "-events.tsv");
  events << "event\tindices\tinstances\tname\n";
  actions(controller->GetRootActions(), events,
          controller->GetStructuredFile());
  events.close();
  GPUCounter counter = GPUCounter::EventGPUDuration;
  bool found = false;
  for (auto c : controller->EnumerateCounters())
    if (controller->DescribeCounter(c).name == "GPUTime") {
      counter = c;
      found = true;
      break;
    }
  if (!found) {
    puts("AMD GPUTime not available");
    controller->Shutdown();
    file->Shutdown();
    RENDERDOC_ShutdownReplay();
    return 4;
  }
  auto desc = controller->DescribeCounter(counter);
  if (desc.unit != CounterUnit::Seconds ||
      desc.resultType != CompType::Float || desc.resultByteWidth != 8) {
    puts("Unsupported GPUTime units");
    return 5;
  }
  double factor = 1000.0;
  printf("Fetching %s unit=%u secondsUnit=%u\n", desc.name.c_str(),
         unsigned(desc.unit), unsigned(CounterUnit::Seconds));
  fflush(stdout);
  auto counters = controller->FetchCounters({counter});
  save_log();
  std::ofstream timings(std::string(argv[2]) + "-timings.tsv");
  timings << "event\tms\n";
  std::vector<std::pair<double, unsigned>> ranked;
  for (const auto &c : counters) {
    double ms = c.value.d * factor;
    timings << c.eventId << '\t' << ms << '\n';
    ranked.push_back({ms, c.eventId});
  }
  timings.close();
  printf("Counter events: %zu\n", ranked.size());
  fflush(stdout);
  if (ranked.empty()) {
    controller->Shutdown();
    file->Shutdown();
    RENDERDOC_ShutdownReplay();
    return 6;
  }
  std::sort(ranked.rbegin(), ranked.rend());
  std::ofstream shaders(std::string(argv[2]) + "-shaders.tsv");
  shaders << "event\tms\tps\tvs\tviewport_width\tviewport_height\n";
  auto name = [&](ResourceId id) {
    for (const auto &r : controller->GetResources())
      if (r.resourceId == id)
        return std::string(r.name.c_str());
    return std::string("unnamed");
  };
  for (size_t i = 0; i < ranked.size() && i < 15; ++i) {
    auto [ms, event] = ranked[i];
    controller->SetFrameEvent(event, true);
    auto state = controller->GetD3D12PipelineState();
    if (!state)
      continue;
    auto ps = name(state->pixelShader.resourceId),
         vs = name(state->vertexShader.resourceId);
    float w = 0, h = 0;
    if (!state->rasterizer.viewports.empty()) {
      w = state->rasterizer.viewports[0].width;
      h = state->rasterizer.viewports[0].height;
    }
    shaders << event << '\t' << ms << '\t' << ps << '\t' << vs << '\t' << w
            << '\t' << h << '\n';
    if (state->pixelShader.reflection) {
      auto dis = controller->DisassembleShader(
          state->pipelineResourceId, state->pixelShader.reflection, "");
      std::ofstream shader(std::string(argv[2]) + "-event" +
                           std::to_string(event) + "-ps.txt");
      shader << dis.c_str();
    }
  }
  shaders.close();
  controller->Shutdown();
  file->Shutdown();
  RENDERDOC_ShutdownReplay();
  return 0;
}
