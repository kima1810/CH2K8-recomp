// Included in rex::ui with the Windows presenter declarations in scope.
void Presenter::DXGIUITickThread() {
  using Pacer=ch2k8::VBlankPacer;
  const bool native_pacing=REXCVAR_GET(ch2k8_native_present_pacing);
  Pacer pacer;
  Microsoft::WRL::ComPtr<IDXGIOutput> observed_output;
  uint32_t refresh_hz=60;
  std::unique_lock<std::mutex> dxgi_ui_tick_lock(dxgi_ui_tick_mutex_);
  while(true) {
    if(dxgi_ui_tick_thread_shutdown_)return;
    if(!AreDXGIUITicksWaitable(dxgi_ui_tick_lock)) {
      observed_output.Reset();
      dxgi_ui_tick_control_condition_.wait(dxgi_ui_tick_lock);
      continue;
    }
    // Retain the output under the lock across both the wait and validation.
    auto output=dxgi_ui_tick_output_;
    if(observed_output.Get()!=output.Get()) {
      observed_output=output;refresh_hz=60;
      if(native_pacing) {
        DXGI_OUTPUT_DESC description{};
        DEVMODEW mode{};mode.dmSize=sizeof(mode);
        if(SUCCEEDED(output->GetDesc(&description)) &&
           EnumDisplaySettingsW(description.DeviceName,ENUM_CURRENT_SETTINGS,&mode) &&
           mode.dmDisplayFrequency>=24 && mode.dmDisplayFrequency<=1000)
          refresh_hz=mode.dmDisplayFrequency;
        pacer.Reset(refresh_hz,Pacer::Clock::now());
      }
    }
    if(native_pacing && pacer.timer()) {
      // A timed condition wait releases the mutex and can be interrupted by
      // shutdown or a new output. Never synthesize catch-up bursts of ticks.
      const auto deadline=pacer.Deadline(Pacer::Clock::now());
      if(dxgi_ui_tick_control_condition_.wait_until(dxgi_ui_tick_lock,deadline,[&] {
          return dxgi_ui_tick_thread_shutdown_ || !AreDXGIUITicksWaitable(dxgi_ui_tick_lock) ||
                 dxgi_ui_tick_output_.Get()!=output.Get();
        }))continue;
      pacer.Delivered(Pacer::Clock::now());
      ++dxgi_ui_tick_last_vblank_;
      dxgi_ui_tick_signal_condition_.notify_all();
      continue;
    }
    const auto before=native_pacing?Pacer::Clock::now():Pacer::Time{};
    dxgi_ui_tick_lock.unlock();
    bool wait_succeeded;
    {
      ch2k8::PresentScope native_vblank_scope(ch2k8::PresentStage::VBlank);
      wait_succeeded=SUCCEEDED(output->WaitForVBlank());
    }
    const auto after=native_pacing?Pacer::Clock::now():Pacer::Time{};
    dxgi_ui_tick_lock.lock();
    // A completion belonging to a replaced output must not signal or reset it.
    if(dxgi_ui_tick_output_.Get()!=output.Get())continue;
    if(wait_succeeded) {
      if(native_pacing && pacer.Observe(before,after)) {
        REXLOG_WARN("CH2K8 native presentation: DXGI VBlank returned immediately; pacing UI at {} Hz",refresh_hz);
        continue;
      }
      ++dxgi_ui_tick_last_vblank_;
    } else {
      dxgi_ui_tick_output_.Reset();
    }
    dxgi_ui_tick_signal_condition_.notify_all();
  }
}
