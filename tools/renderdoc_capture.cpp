// Local, process-checked frame capture via the public RenderDoc replay API.
#include "renderdoc_replay.h"
#include <chrono>
#include <cstdio>
#include <windows.h>
int main(int argc, char **argv) {
  if (argc != 4) {
    puts("Usage: renderdoc_capture <local-port> <expected-game-pid> "
         "<frames:1-8>");
    return 1;
  }
  if (atoi(argv[3]) < 1 || atoi(argv[3]) > 8)
    return 1;
  auto control = RENDERDOC_CreateTargetControl("", unsigned(atoi(argv[1])),
                                               "CH2K8Research", false);
  if (!control) {
    puts("Target connection failed");
    return 2;
  }
  printf("Connected target=%s PID=%u API=%s\n", control->GetTarget().c_str(),
         control->GetPID(), control->GetAPI().c_str());
  fflush(stdout);
  if ((control->GetPID() != unsigned(atoi(argv[2])) ||
       control->GetTarget() != "ch2k8")) {
    control->Shutdown();
    return 3;
  }
  int remaining = atoi(argv[3]);
  const auto requested_at = std::chrono::duration_cast<std::chrono::seconds>(
      std::chrono::system_clock::now().time_since_epoch()).count();
  control->TriggerCapture(remaining);
  auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(50);
  while (control->Connected() && std::chrono::steady_clock::now() < deadline) {
    auto msg = control->ReceiveMessage();
    if (msg.type == TargetControlMessageType::NewCapture) {
      // Connecting also announces existing captures. Never mistake one of
      // those for the result of this request (timestamps have second precision).
      if (msg.newCapture.timestamp < uint64_t(requested_at))
        continue;
      printf("Capture: %s frame=%u bytes=%llu\n", msg.newCapture.path.c_str(),
             msg.newCapture.frameNumber,
             (unsigned long long)msg.newCapture.byteSize);
      fflush(stdout);
      if (--remaining == 0) {
        control->Shutdown();
        return 0;
      }
    }
  }
  control->Shutdown();
  puts("No completed capture received");
  return 4;
}
