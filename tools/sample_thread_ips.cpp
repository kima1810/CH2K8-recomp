// Bounded instruction-pointer sampling of explicitly selected CH2K8 threads.
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <windows.h>

#include <tlhelp32.h>
struct Module {
  uintptr_t base, end;
  std::string name;
};
int main(int argc, char **argv) {
  if (argc < 3)
    return 1;
  int samples = 30, interval = 100;
  std::vector<DWORD> requested;
  for (int i = 2; i < argc; ++i) {
    if (!strcmp(argv[i], "--samples") || !strcmp(argv[i], "--interval")) {
      bool count = !strcmp(argv[i], "--samples");
      if (++i >= argc)
        return 1;
      if (count)
        samples = atoi(argv[i]);
      else
        interval = atoi(argv[i]);
    } else {
      DWORD tid = atoi(argv[i]);
      if (!tid)
        return 1;
      requested.push_back(tid);
    }
  }
  if (requested.empty() || samples < 1 || samples > 1000 || interval < 1 ||
      interval > 1000 || samples * interval > 30000)
    return 1;
  DWORD pid = atoi(argv[1]);
  HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
  if (!process)
    return 2;
  char image[MAX_PATH];
  DWORD length = MAX_PATH;
  bool valid = QueryFullProcessImageNameA(process, 0, image, &length);
  CloseHandle(process);
  if (!valid)
    return 2;
  const char *name = strrchr(image, '\\');
  name = name ? name + 1 : image;
  if (_stricmp(name, "ch2k8.exe"))
    return 3;
  std::vector<DWORD> allowed;
  HANDLE threads = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
  THREADENTRY32 entry{};
  entry.dwSize = sizeof(entry);
  if (Thread32First(threads, &entry))
    do {
      if (entry.th32OwnerProcessID == pid)
        allowed.push_back(entry.th32ThreadID);
    } while (Thread32Next(threads, &entry));
  CloseHandle(threads);
  std::vector<Module> modules;
  HANDLE snapshot =
      CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
  MODULEENTRY32 m{};
  m.dwSize = sizeof(m);
  if (Module32First(snapshot, &m))
    do {
      modules.push_back({uintptr_t(m.modBaseAddr),
                         uintptr_t(m.modBaseAddr) + m.modBaseSize, m.szModule});
    } while (Module32Next(snapshot, &m));
  CloseHandle(snapshot);
  puts("sample,thread,module,rva");
  for (int sample = 0; sample < samples; ++sample) {
    for (DWORD tid : requested) {
      if (std::find(allowed.begin(), allowed.end(), tid) == allowed.end())
        continue;
      HANDLE t = OpenThread(THREAD_GET_CONTEXT | THREAD_SUSPEND_RESUME |
                                THREAD_QUERY_INFORMATION,
                            FALSE, tid);
      if (!t)
        continue;
      if (GetProcessIdOfThread(t) != pid) {
        CloseHandle(t);
        continue;
      }
      CONTEXT c{};
      c.ContextFlags = CONTEXT_CONTROL;
      bool got = false;
      if (SuspendThread(t) != DWORD(-1)) {
        got = GetThreadContext(t, &c);
        ResumeThread(t);
      }
      CloseHandle(t);
      if (got) {
        const char *name = "unknown";
        uintptr_t base = 0;
        for (const auto &mod : modules)
          if (c.Rip >= mod.base && c.Rip < mod.end) {
            name = mod.name.c_str();
            base = mod.base;
            break;
          }
        printf("%d,%lu,%s,0x%llx\n", sample, tid, name,
               (unsigned long long)(c.Rip - base));
      }
    }
    Sleep(interval);
  }
  return 0;
}
