#include "renderdoc_replay.h"
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <map>
#include <string>
REPLAY_PROGRAM_MARKER();
int main(int argc, char **argv) {
  if (argc != 3)
    return 1;
  RENDERDOC_InitialiseReplay(GlobalEnvironment{}, {});
  auto file = RENDERDOC_OpenCaptureFile();
  auto opened = file->OpenFile(argv[1], "rdc");
  if (!opened.OK())
    return 2;
  auto replay = file->OpenCapture(ReplayOptions{});
  if (!replay.first.OK())
    return 3;
  auto controller = replay.second;
  rdcarray<GPUCounter> requested;
  std::map<GPUCounter, CounterDescription> descriptions;
  for (auto id : controller->EnumerateCounters()) {
    auto d = controller->DescribeCounter(id);
    if (d.name == "GPUTime" || d.name == "ExecutionDuration" ||
        d.name == "ExecutionStart" || d.name == "ExecutionEnd") {
      requested.push_back(id);
      descriptions[id] = d;
      printf("%s unit=%u type=%u bytes=%u\n", d.name.c_str(), unsigned(d.unit),
             unsigned(d.resultType), d.resultByteWidth);
    }
  }
  fflush(stdout);
  std::map<std::string, size_t> chunks;
  for (auto c : controller->GetStructuredFile().chunks)
    ++chunks[c->name.c_str()];
  std::ofstream histogram(std::string(argv[2]) + "-chunks.tsv");
  histogram << "chunk\tcount\n";
  for (const auto &item : chunks)
    histogram << item.first << '\t' << item.second << '\n';
  histogram.close();
  if (requested.size() != 4)
    return 4;
  auto values = controller->FetchCounters(requested);
  std::ofstream out(argv[2]);
  out << std::setprecision(17) << "event\tcounter\tvalue\tunit\n";
  for (const auto &v : values) {
    auto d = descriptions[v.counter];
    out << v.eventId << '\t' << d.name.c_str() << '\t';
    if (d.resultType == CompType::Float && d.resultByteWidth == 8)
      out << v.value.d;
    else if (d.resultType == CompType::UInt)
      out << v.value.u64;
    else
      out << "NA";
    out << '\t' << unsigned(d.unit) << '\n';
  }
  out.close();
  printf("Records %zu\n", values.size());
  controller->Shutdown();
  file->Shutdown();
  RENDERDOC_ShutdownReplay();
  return values.empty() ? 5 : 0;
}
