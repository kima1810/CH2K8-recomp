"""Apply bounded native PCM substitution to the pinned recomp source SDK."""
from pathlib import Path


def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Unrecognized native PCM patch site: '+old[:80])
    return text.replace(old,new,1)


def prepare_native_pcm(source):
    header=source/'include/rex/audio/xma/context.h';text=header.read_text(encoding='utf-8')
    if '// CH2K8 native PCM v1' not in text:
        text=once(text,'#include <rex/thread.h>','#include <rex/thread.h>\n#include <rex/audio/ch2k8_native_pcm.h>\n// CH2K8 native PCM v1')
        text=once(text,'  std::array<uint8_t, kBytesPerFrameChannel * 2> raw_frame_;','  ::ch2k8::PCMStream native_pcm_;\n  std::array<uint8_t, kBytesPerFrameChannel * 2> raw_frame_;')
        header.write_text(text,encoding='utf-8',newline='\n')
    cpp=source/'src/audio/xma_context.cpp';text=cpp.read_text(encoding='utf-8')
    if '// CH2K8 native PCM v1' not in text:
        text=once(text,'void XmaContext::ResetDecoderState() {','void XmaContext::ResetDecoderState() {\n  native_pcm_.Reset();\n  // CH2K8 native PCM v1')
        text=once(text,'  const uint8_t skip_count = xma::GetPacketSkipCount(packet);','''  try {
    native_pcm_.Observe(reinterpret_cast<uintptr_t>(current_input_buffer),data->input_buffer_read_offset);
    if(data->loop_count) native_pcm_.Disable();
    else {
      const bool was_active=native_pcm_.active();
      if(native_pcm_.Consider(std::span<const uint8_t>(current_input_buffer,current_input_size),1u+data->is_stereo,
          packet_index==0 && relative_offset==packet_first_frame_offset) && !was_active)
        REXAPU_INFO("Native PCM WAV matched Xbox XMA stream");
    }
  } catch(const std::exception& error) {
    native_pcm_.Disable(); REXAPU_ERROR("Native PCM rejected: {}",error.what());
  }
  const uint8_t skip_count = xma::GetPacketSkipCount(packet);''')
        text=once(text,'      current_frame_remaining_subframes_ = 4 << data->is_stereo;','''      native_pcm_.Apply(std::span<uint8_t>(raw_frame_.data(),kBytesPerFrameChannel*(1u+data->is_stereo)),kSamplesPerFrame,1u+data->is_stereo);
      current_frame_remaining_subframes_ = 4 << data->is_stereo;''')
        cpp.write_text(text,encoding='utf-8',newline='\n')
    destination=source/'include/rex/audio/ch2k8_native_pcm.h'
    here=Path(__file__).resolve().parent
    candidates=[here/'native_pcm.h',here.parent/'port/src/native_pcm.h']
    origin=next((p for p in candidates if p.is_file()),None)
    if origin is None:raise ValueError('Native PCM source header missing')
    destination.write_bytes(origin.read_bytes())
