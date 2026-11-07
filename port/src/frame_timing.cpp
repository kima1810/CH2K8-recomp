#include <atomic>
#include <chrono>
#include <cstdio>
#include <mutex>
#ifdef _WIN32
#include <windows.h>
#endif

namespace {
using Clock = std::chrono::steady_clock;
std::mutex mutex;
std::atomic<bool> enabled{false};
std::FILE *output = nullptr;
Clock::time_point origin;
thread_local Clock::time_point before, previous;
thread_local double cpu_before = 0;
double cpu_ms() {
#ifdef _WIN32
  FILETIME created{}, exited{}, kernel{}, user{};
  if (GetThreadTimes(GetCurrentThread(), &created, &exited, &kernel, &user)) {
    ULARGE_INTEGER k{}, u{};
    k.LowPart = kernel.dwLowDateTime;
    k.HighPart = kernel.dwHighDateTime;
    u.LowPart = user.dwLowDateTime;
    u.HighPart = user.dwHighDateTime;
    return double(k.QuadPart + u.QuadPart) / 10000.0;
  }
#endif
  return 0;
}
} // namespace

bool Ch2k8OpenFrameLog(const char *path) {
  std::lock_guard lock(mutex);
#ifdef _WIN32
  fopen_s(&output, path, "w");
#else
  output = std::fopen(path, "w");
#endif
  if (!output)
    return false;
  std::fputs("elapsed_ms,submit_interval_ms,swap_wall_ms,swap_thread_cpu_ms\n",
             output);
  origin = Clock::now();
  enabled.store(true, std::memory_order_release);
  return true;
}

void Ch2k8CloseFrameLog() {
  enabled.store(false, std::memory_order_release);
  std::lock_guard lock(mutex);
  if (output) {
    std::fclose(output);
    output = nullptr;
  }
}

void Ch2k8BeforeSwap() {
  if (!enabled.load(std::memory_order_acquire))
    return;
  before = Clock::now();
  cpu_before = cpu_ms();
}

void Ch2k8AfterSwap() {
  if (!enabled.load(std::memory_order_acquire))
    return;
  const auto after = Clock::now();
  const double cpu = cpu_ms() - cpu_before;
  const auto ms = [](auto duration) {
    return std::chrono::duration<double, std::milli>(duration).count();
  };
  std::lock_guard lock(mutex);
  if (!output)
    return;
  std::fprintf(output, "%.3f,%.3f,%.3f,%.3f\n", ms(after - origin),
               previous == Clock::time_point{} ? 0.0 : ms(before - previous),
               ms(after - before), cpu);
  std::fflush(output);
  previous = before;
}
