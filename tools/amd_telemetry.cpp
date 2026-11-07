// Read-only RX 6650 XT sensors via the installed AMD ADL driver. Requires
// official ADL SDK headers.
#include "adl_sdk.h"
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <windows.h>
void *__stdcall alloc(int n) { return malloc(n); }
int main(int argc, char **argv) {
  auto dll =
      LoadLibraryExW(L"atiadlxx.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (!dll)
    return 1;
  auto create =
      (int(__stdcall *)(ADL_MAIN_MALLOC_CALLBACK, int, void **))GetProcAddress(
          dll, "ADL2_Main_Control_Create");
  auto destroy = (int(__stdcall *)(void *))GetProcAddress(
      dll, "ADL2_Main_Control_Destroy");
  auto count = (int(__stdcall *)(void *, int *))GetProcAddress(
      dll, "ADL2_Adapter_NumberOfAdapters_Get");
  auto info = (int(__stdcall *)(void *, AdapterInfo *, int))GetProcAddress(
      dll, "ADL2_Adapter_AdapterInfo_Get");
  auto query =
      (int(__stdcall *)(void *, int, ADLPMLogDataOutput *))GetProcAddress(
          dll, "ADL2_New_QueryPMLogData_Get");
  if (!create || !destroy || !count || !info || !query) {
    puts("Telemetry API unavailable");
    return 2;
  }
  void *context = nullptr;
  if (create(alloc, 1, &context) != 0)
    return 3;
  int n = 0;
  if (count(context, &n) != 0 || n < 1 || n > 256) {
    destroy(context);
    return 4;
  }
  std::vector<AdapterInfo> adapters(n);
  for (auto &a : adapters)
    a.iSize = sizeof(a);
  info(context, adapters.data(), sizeof(AdapterInfo) * n);
  int adapter = -1;
  for (const auto &a : adapters)
    if (strstr(a.strAdapterName, "RX 6650 XT")) {
      adapter = a.iAdapterIndex;
      break;
    }
  if (adapter < 0) {
    puts("Target adapter not found");
    destroy(context);
    return 4;
  }
  puts("second,gfx_clock_raw,mem_clock_raw,gfx_activity_raw,edge_temp_raw,"
       "hotspot_temp_raw,asic_power_raw,throttler_raw");
  int seconds = argc > 1 ? atoi(argv[1]) : 3;
  if (seconds < 1 || seconds > 3600) {
    destroy(context);
    return 5;
  }
  for (int i = 0; i < seconds; ++i) {
    ADLPMLogDataOutput data{};
    data.size = sizeof(data);
    int status = query(context, adapter, &data);
    if (status != 0) {
      printf("Query error %d\n", status);
      break;
    }
    printf("%d", i);
    for (int sensor : {1, 2, 19, 8, 27, 23, 35}) {
      if (data.sensors[sensor].supported)
        printf(",%d", data.sensors[sensor].value);
      else
        printf(",NA");
    }
    puts("");
    fflush(stdout);
    Sleep(1000);
  }
  destroy(context);
  return 0;
}
