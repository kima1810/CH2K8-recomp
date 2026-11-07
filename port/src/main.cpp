#include "native_gpu_wait.h"
// ch2k8 - ReXGlue Recompiled Project
//
// Minimal app: boots the recompiled default.xex through the Xenos GPU plugin.
// Customize by overriding virtual hooks from rex::ReXApp (see the SvR 2008
// port's svr2008_app.h).

#include "generated/default/ch2k8_init.h"

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/rex_app.h>
#include <rex/system.h>
#include <rex/runtime.h>
#include <rex/filesystem.h>
#include <rex/system/gpu_plugin.h>
#include <rex/ui/presenter.h>

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <memory>
#include <thread>

REXCVAR_DEFINE_BOOL(ch2k8_native_gpu_wait,true,"CH2K8/Performance",
                    "Wait for native GPU progress instead of repeatedly polling")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_BOOL(ch2k8_gpu_wait_stats,false,"CH2K8/Diagnostics",
                    "Opt-in aggregate native GPU wait timings");
void Ch2k8LogGpuWait(const Ch2k8GpuWaitStats& stats) {
  REXLOG_INFO("CH2K8_GPU_WAIT waits={} notifications={} timeouts={} wall_ms={} address={:X} window_ms={} cpu_ms={}",
      stats.waits,stats.notifications,stats.timeouts,stats.wall_ms,stats.counter_address,
      stats.window_ms,stats.thread_cpu_ms);
}
REXCVAR_DEFINE_STRING(ch2k8_renderer, "d3d12", "CH2K8/Graphics",
                      "Native graphics backend: d3d12 or vulkan")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_BOOL(ch2k8_native_dds, true, "CH2K8/Graphics",
                    "Use native DDS replacements from a loose Xbox installation (D3D12)")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_BOOL(ch2k8_native_audio,true,"CH2K8/Audio","Use native fixed-duration PCM WAV resources")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

bool Ch2k8OpenFrameLog(const char *path);
bool Ch2k8MountLooseAssets(rex::Runtime& runtime);
void Ch2k8CloseFrameLog();
void Ch2k8ConfigureHotFunctions(int selected_mode, int selected_unpack,
                                int selected_store, int selected_ram,
                                bool selected_guarded_store, const char *path);
void Ch2k8CloseHotLog();
void Ch2k8ConfigureGeometryBatch(int);
REXCVAR_DEFINE_STRING(ch2k8_geometry_batch, "optimized", "CH2K8/Performance",
                      "Exact normalization batching: baseline, optimized, compare")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_STRING(ch2k8_vector_pack, "optimized", "CH2K8/Performance",
                      "Packed-vector path: baseline, optimized, or compare")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_STRING(ch2k8_hot_log, "", "CH2K8/Diagnostics",
                      "Opt-in per-thread hot-function aggregate CSV");
REXCVAR_DEFINE_STRING(
    ch2k8_vector_unpack, "optimized", "CH2K8/Performance",
    "Unpack path within optimized packing: baseline, optimized, or compare")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_STRING(ch2k8_vector_store, "optimized", "CH2K8/Performance",
                      "Aligned byte-store path within optimized unpack: "
                      "baseline, optimized, or compare")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
bool Ch2k8SaveOutput(rex::ui::Presenter *presenter, const char *path);
REXCVAR_DEFINE_STRING(ch2k8_ram_store, "optimized", "CH2K8/Performance",
                      "Guarded RAM vector stores: baseline, optimized, or compare")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_BOOL(ch2k8_guarded_vector_store, true, "CH2K8/Performance",
                    "Enable checked stack-reload vector stores in FUN_84724930")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_STRING(ch2k8_output_capture, "", "CH2K8/Diagnostics",
                      "Opt-in native guest-output BMP filename prefix");
REXCVAR_DEFINE_INT32(ch2k8_output_capture_delay, 60, "CH2K8/Diagnostics",
                     "Seconds before native output readback")
    .range(0, 3600);
REXCVAR_DEFINE_INT32(ch2k8_output_capture_count, 1, "CH2K8/Diagnostics",
                     "Number of native output readbacks")
    .range(1, 10);
REXCVAR_DEFINE_INT32(ch2k8_output_capture_interval, 60, "CH2K8/Diagnostics",
                     "Seconds between native output readbacks")
    .range(1, 3600);
REXCVAR_DEFINE_STRING(
    ch2k8_frame_log, "", "CH2K8/Diagnostics",
    "Opt-in CSV of guest VdSwap intervals and call wall/CPU time");

#ifdef _WIN32
#include "../third_party/renderdoc_app.h"
#include <rex/ui/d3d12/d3d12_provider.h>
#if REX_HAS_VULKAN
#include <rex/ui/vulkan/provider.h>
#endif
#include <windows.h>

REXCVAR_DEFINE_STRING(
    ch2k8_gpu_capture, "", "CH2K8/Diagnostics",
    "Opt-in RenderDoc capture filename prefix (requires injected RenderDoc)");
REXCVAR_DEFINE_STRING(ch2k8_gpu_capture_trigger, "", "CH2K8/Diagnostics",
    "Optional filename: begin the device capture when this file exists");
REXCVAR_DEFINE_INT32(
    ch2k8_gpu_capture_delay, 120, "CH2K8/Diagnostics",
    "Seconds after runtime setup before an automated GPU capture")
    .range(0, 3600);
#endif

class Ch2k8App : public rex::ReXApp {
public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp>
  Create(rex::ui::WindowedAppContext &ctx) {
    return std::unique_ptr<Ch2k8App>(
        new Ch2k8App(ctx, "ch2k8", PPCImageConfig));
  }

protected:
  void OnPreSetup(rex::RuntimeConfig &config) override {
    const auto renderer = REXCVAR_GET(ch2k8_renderer);
    const auto asset_root=rex::to_path(REXCVAR_GET(game_data_root));
    const bool native_dds=REXCVAR_GET(ch2k8_native_dds) && renderer=="d3d12" &&
        std::filesystem::exists(asset_root/"assets.map");
#if !CH2K8_HAS_NATIVE_DDS
    if (native_dds) {
      const std::string message="Native DDS needs the patched source SDK. Build the win-amd64-vulkan preset or disable ch2k8_native_dds.";
      REXLOG_ERROR("{}",message);
      rex::ShowSimpleMessageBox(rex::SimpleMessageBoxType::Error,message);
      std::exit(EXIT_FAILURE);
    }
#endif
    // Set this before initializing the GPU plugin, whose lazy DDS catalog is
    // private to its DLL. The folder VFS remains active when DDS is disabled.
#ifdef _WIN32
    const bool native_audio=REXCVAR_GET(ch2k8_native_audio) && std::filesystem::exists(asset_root/"assets.map");
    _wputenv_s(L"CH2K8_ASSET_ROOT",native_dds || native_audio?asset_root.c_str():L"");
    _putenv_s("CH2K8_NATIVE_DDS",native_dds?"1":"0");
    _putenv_s("CH2K8_NATIVE_AUDIO",native_audio?"1":"0");
#else
    const bool native_audio=REXCVAR_GET(ch2k8_native_audio) && std::filesystem::exists(asset_root/"assets.map");
    setenv("CH2K8_ASSET_ROOT",native_dds || native_audio?asset_root.c_str():"",1);
    setenv("CH2K8_NATIVE_DDS",native_dds?"1":"0",1);
    setenv("CH2K8_NATIVE_AUDIO",native_audio?"1":"0",1);
#endif
    if (renderer == "d3d12" || renderer == "vulkan") {
      config.graphics = rex::system::LoadGpuPlugin("xenos", renderer);
      if (config.graphics) {
        REXLOG_INFO("CH2K8 selected native renderer: {}", renderer);
        return;
      }
    }
    const auto message =
        "CH2K8 renderer '" + renderer +
        "' is unavailable. Vulkan requires the Vulkan-capable SDK build. "
        "See the runtime log.";
    REXLOG_ERROR("{}", message);
    rex::ShowSimpleMessageBox(rex::SimpleMessageBoxType::Error, message);
    // OnPreSetup has no failure return; prevent the SDK from falling back
    // to its default backend after an explicit renderer request fails.
    std::exit(EXIT_FAILURE);
  }

  void OnPostSetup() override {
    if (!Ch2k8MountLooseAssets(*runtime())) std::exit(EXIT_FAILURE);
    const auto pack = REXCVAR_GET(ch2k8_vector_pack);
    const auto unpack = REXCVAR_GET(ch2k8_vector_unpack);
    const auto store = REXCVAR_GET(ch2k8_vector_store);
    const auto ram = REXCVAR_GET(ch2k8_ram_store);
    if (ram != "baseline" && ram != "optimized" && ram != "compare") {
      REXLOG_ERROR("Invalid ch2k8_ram_store: {}", ram);
      std::exit(EXIT_FAILURE);
    }
    if (store != "baseline" && store != "optimized" && store != "compare") {
      REXLOG_ERROR("Invalid ch2k8_vector_store: {}", store);
      std::exit(EXIT_FAILURE);
    }
    if (pack != "baseline" && pack != "optimized" && pack != "compare") {
      REXLOG_ERROR("Invalid ch2k8_vector_pack: {}", pack);
      std::exit(EXIT_FAILURE);
    }
    if (unpack != "baseline" && unpack != "optimized" && unpack != "compare") {
      REXLOG_ERROR("Invalid ch2k8_vector_unpack: {}", unpack);
      std::exit(EXIT_FAILURE);
    }
    const auto batch=REXCVAR_GET(ch2k8_geometry_batch);
    if(batch!="baseline" && batch!="optimized" && batch!="compare") {
      REXLOG_ERROR("Invalid ch2k8_geometry_batch: {}",batch);std::exit(EXIT_FAILURE);
    }
    Ch2k8ConfigureGpuWait(REXCVAR_GET(ch2k8_native_gpu_wait),
        REXCVAR_GET(ch2k8_gpu_wait_stats)?Ch2k8LogGpuWait:nullptr);
    Ch2k8ConfigureGeometryBatch(batch=="compare"?2:batch=="optimized"?1:0);
    Ch2k8ConfigureHotFunctions(pack == "compare"     ? 2
                               : pack == "optimized" ? 1
                                                     : 0,
                               unpack == "compare"     ? 2
                               : unpack == "optimized" ? 1
                                                       : 0,
                               store == "compare"     ? 2
                               : store == "optimized" ? 1
                                                      : 0,
                               ram == "compare" ? 2 : ram == "optimized" ? 1 : 0,
                               REXCVAR_GET(ch2k8_guarded_vector_store),
                               REXCVAR_GET(ch2k8_hot_log).c_str());
    REXLOG_INFO("CH2K8 packed-vector path: {}", pack);
    REXLOG_INFO("CH2K8 vector-unpack path: {}", unpack);
    REXLOG_INFO("CH2K8 vector-store path: {}", store);
    REXLOG_INFO("CH2K8 guarded RAM-store path: {}", ram);
    REXLOG_INFO("CH2K8 checked vector reloads: {}", REXCVAR_GET(ch2k8_guarded_vector_store));
    const auto output_prefix = REXCVAR_GET(ch2k8_output_capture);
    auto graphics = runtime()->graphics_system();
    if (!output_prefix.empty() && graphics && graphics->presenter()) {
      auto presenter = graphics->presenter();
      const int delay = REXCVAR_GET(ch2k8_output_capture_delay);
      const int count = REXCVAR_GET(ch2k8_output_capture_count);
      const int interval = REXCVAR_GET(ch2k8_output_capture_interval);
      output_thread_ = std::jthread([presenter, output_prefix, delay, count,
                                     interval](std::stop_token stop) {
        using namespace std::chrono_literals;
        for (int image = 0; image < count; ++image) {
          for (int tick = 0; tick < (image ? interval : delay) * 10; ++tick) {
            if (stop.stop_requested())
              return;
            std::this_thread::sleep_for(100ms);
          }
          if (stop.stop_requested())
            return;
          const auto path =
              output_prefix + "-" + std::to_string(image) + ".bmp";
          const bool success = Ch2k8SaveOutput(presenter, path.c_str());
          REXLOG_INFO("CH2K8 native output capture: {} success={}", path,
                      success);
        }
      });
    }
    const auto frame_log = REXCVAR_GET(ch2k8_frame_log);
    if (!frame_log.empty() && !Ch2k8OpenFrameLog(frame_log.c_str()))
      REXLOG_WARN("CH2K8 frame log could not be opened: {}", frame_log);
    // GPU-plugin flags register dynamically; report their effective values
    // after setup so rendering comparisons can verify the requested profile.
    for (const auto *name :
         {"render_target_path_d3d12", "render_target_path_vulkan",
          "async_shader_compilation", "readback_resolve", "readback_memexport",
          "readback_memexport_fast", "d3d12_bindless",
          "ch2k8_native_constants", "ch2k8_native_packets",
          "ch2k8_packet_compare", "ch2k8_gpu_stats",
          "ch2k8_present_stats",
          "ch2k8_native_present_pacing", "ch2k8_native_gpu_wait", "ch2k8_gpu_wait_stats", "ch2k8_geometry_batch",
          "ch2k8_native_pixel_state", "ch2k8_native_depth_state",
          "ch2k8_native_full_write",
          "ch2k8_native_vertex_fetch", "ch2k8_vertex_fetch_compare",
          "d3d12_submit_on_primary_buffer_end",
          "vulkan_submit_on_primary_buffer_end", "vulkan_dynamic_rendering",
          "occlusion_query_enable", "host_present_from_non_ui_thread",
          "draw_resolution_scale_x", "draw_resolution_scale_y", "dxbc_switch",
          "d3d12_pipeline_creation_threads",
          "execute_unclipped_draw_vs_on_cpu", "video_mode_refresh_rate",
          "ch2k8_guest_refresh_rate", "d3d12_adapter", "vsync"}) {
      REXLOG_INFO("CH2K8 rendering configuration: {}={}", name,
                  rex::cvar::GetFlagByName(name));
    }
#ifdef _WIN32
    const auto prefix = REXCVAR_GET(ch2k8_gpu_capture);
    if (!prefix.empty()) {
      auto module = GetModuleHandleW(L"renderdoc.dll");
      auto get_api = module ? reinterpret_cast<pRENDERDOC_GetAPI>(
                                  GetProcAddress(module, "RENDERDOC_GetAPI"))
                            : nullptr;
      RENDERDOC_API_1_6_0 *capture = nullptr;
      auto graphics = runtime()->graphics_system();
      RENDERDOC_DevicePointer device = nullptr;
      if (graphics) {
        if (auto provider = dynamic_cast<rex::ui::d3d12::D3D12Provider *>(
                graphics->provider())) {
          device = provider->GetDevice();
        }
#if REX_HAS_VULKAN
        if (auto provider = dynamic_cast<rex::ui::vulkan::VulkanProvider *>(
                graphics->provider())) {
          device = RENDERDOC_DEVICEPOINTER_FROM_VKINSTANCE(
              provider->vulkan_instance()->instance());
        }
#endif
      }
      if (!get_api ||
          !get_api(eRENDERDOC_API_Version_1_6_0,
                   reinterpret_cast<void **>(&capture)) ||
          !device) {
        REXLOG_WARN("CH2K8 GPU capture unavailable: requires injected "
                    "RenderDoc and a supported native graphics provider");
        return;
      }
      const int delay = REXCVAR_GET(ch2k8_gpu_capture_delay);
      const auto trigger = REXCVAR_GET(ch2k8_gpu_capture_trigger);
      capture_thread_ =
          std::jthread([capture, device, prefix, delay, trigger](std::stop_token stop) {
            using namespace std::chrono_literals;
            for (int tick = 0; trigger.empty() && tick < delay * 10; ++tick) {
              if (stop.stop_requested())
                return;
              std::this_thread::sleep_for(100ms);
            }
            while (!trigger.empty() && !stop.stop_requested()) {
              std::error_code error;
              if (std::filesystem::is_regular_file(trigger, error)) break;
              std::this_thread::sleep_for(100ms);
            }
            if (stop.stop_requested() || capture->IsFrameCapturing())
              return;
            capture->SetCaptureFilePathTemplate(prefix.c_str());
            REXLOG_INFO("CH2K8 GPU capture: starting timed device capture");
            capture->StartFrameCapture(device, nullptr);
            if (!capture->IsFrameCapturing()) {
              REXLOG_WARN("CH2K8 GPU capture: start failed");
              return;
            }
            // Capture off-screen guest submissions across host presentation
            // calls.
            for (int tick = 0; tick < (trigger.empty() ? 8 : 50) && !stop.stop_requested(); ++tick)
              std::this_thread::sleep_for(100ms);
            const auto success = capture->EndFrameCapture(device, nullptr);
            REXLOG_INFO("CH2K8 GPU capture: completed success={}", success);
          });
    }
#endif
  }

  void OnShutdown() override {
    Ch2k8CloseHotLog();
    Ch2k8CloseFrameLog();
    output_thread_.request_stop();
    if (output_thread_.joinable())
      output_thread_.join();
    // Join before the runtime releases the device used by the capture thread.
    capture_thread_.request_stop();
    if (capture_thread_.joinable())
      capture_thread_.join();
  }

private:
  std::jthread output_thread_;
  std::jthread capture_thread_;
};

REX_DEFINE_APP(ch2k8, Ch2k8App::Create)
