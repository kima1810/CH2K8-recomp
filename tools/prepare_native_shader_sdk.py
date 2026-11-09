"""Checked per-draw ROV shader specialization for the pinned source SDK."""
from pathlib import Path
import subprocess
from prepare_native_gpu_sdk import replace_once

ROOT = Path(__file__).resolve().parents[1]


def patch_header_v3(text):
    text = replace_once(text, '#pragma once', '#pragma once\n#include <rex/graphics/native_pixel_state.h>\n#include <rex/graphics/pipeline/render_target/cache.h>')
    text = replace_once(text, 'kVersion = 0x20260226;', 'kVersion = 0x20261103;')
    text = replace_once(text, '      DepthStencilMode depth_stencil_mode : 2;',
                        '      DepthStencilMode depth_stencil_mode : 2;\n'
                        '      uint32_t native_pixel_state : 16;')
    signature = '  dxbc::Src LoadSystemConstant(SystemConstants::Index index, size_t offset, uint32_t swizzle) {\n'
    text = replace_once(text, signature, signature+'''    // CH2K8 exact-state shader specialization v3
    if (current_shader().type() == xenos::ShaderType::kPixel && edram_rov_used_) {
      const auto state = GetDxbcShaderModification().pixel.native_pixel_state;
      if (ch2k8::PixelStateEnabled(state) && swizzle == dxbc::Src::kXXXX) {
        if (index == SystemConstants::Index::kEdramRTFormatFlags &&
            offset == offsetof(SystemConstants, edram_rt_format_flags)) {
          return dxbc::Src::LU(RenderTargetCache::AddPSIColorFormatFlags(
              xenos::ColorRenderTargetFormat(ch2k8::ColorFormat(state))));
        }
        if (index == SystemConstants::Index::kEdramRTBlendFactorsOps &&
            offset == offsetof(SystemConstants, edram_rt_blend_factors_ops) &&
            ch2k8::HasBlend(state)) return dxbc::Src::LU(ch2k8::BlendControl(state));
      }
    }
    if (current_shader().type() == xenos::ShaderType::kPixel && edram_rov_used_ &&
        index == SystemConstants::Index::kSampleCountLog2 &&
        offset == offsetof(SystemConstants, sample_count_log2)) {
      const auto state = GetDxbcShaderModification().pixel.native_pixel_state;
      if (ch2k8::CanFoldSamples(state, swizzle)) {
        return dxbc::Src::LU(ch2k8::SampleLog2(state, swizzle & 3),
            ch2k8::SampleLog2(state, (swizzle >> 2) & 3),
            ch2k8::SampleLog2(state, (swizzle >> 4) & 3),
            ch2k8::SampleLog2(state, (swizzle >> 6) & 3));
      }
    }
''')
    before = '  dxbc::Src LoadFlagsSystemConstant() {\n'
    text = replace_once(text, before, '''  dxbc::Src LoadMaskedFlagsSystemConstant(uint32_t mask) {
    if (current_shader().type() == xenos::ShaderType::kPixel && edram_rov_used_) {
      const auto state = GetDxbcShaderModification().pixel.native_pixel_state;
      if (ch2k8::CanFoldFlags(state, mask)) return dxbc::Src::LU(ch2k8::PixelFlags(state));
    }
    return LoadFlagsSystemConstant();
  }
'''+before)
    return text


def patch_pipeline_v3(text):
    text = replace_once(text, 'REXCVAR_DEFINE_BOOL(d3d12_dxbc_disasm,', '''REXCVAR_DEFINE_BOOL(ch2k8_native_pixel_state, true, "GPU/CH2K8",
                    "Specialize exact ROV sample, format, alpha and common blend state")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

REXCVAR_DEFINE_BOOL(d3d12_dxbc_disasm,''')
    start = text.index('DxbcShaderTranslator::Modification PipelineCache::GetCurrentPixelShaderModification(')
    end = text.index('\n}\n', start)
    part = text[start:end]
    part = replace_once(part, '  return modification;', '''  // CH2K8 exact-state shader specialization v3
  if (REXCVAR_GET(ch2k8_native_pixel_state) &&
      render_target_cache_.GetPath() == RenderTargetCache::Path::kPixelShaderInterlock) {
    static_assert(DxbcShaderTranslator::kSysFlag_DepthFloat24_Shift == 6);
    static_assert(DxbcShaderTranslator::kSysFlag_AlphaPassIfLess_Shift == 7);
    static_assert(uint32_t(xenos::BlendOp::kMin) == 2);
    static_assert(uint32_t(xenos::BlendFactor::kSrcAlpha) == 6);
    const auto color = regs.Get<reg::RB_COLORCONTROL>();
    uint32_t flags = uint32_t(regs.Get<reg::RB_DEPTH_INFO>().depth_format ==
        xenos::DepthRenderTargetFormat::kD24FS8) << 6;
    flags |= uint32_t(color.alpha_test_enable ? color.alpha_func :
        xenos::CompareFunction::kAlways) << 7;
    const auto rt0 = regs.Get<reg::RB_COLOR_INFO>(reg::RB_COLOR_INFO::rt_register_indices[0]);
    modification.pixel.native_pixel_state = ch2k8::PackPixelState(
        uint32_t(regs.Get<reg::RB_SURFACE_INFO>().msaa_samples), flags,
        uint32_t(rt0.color_format),
        regs[reg::RB_BLENDCONTROL::rt_register_indices[0]] & 0x1FFF1FFFu);
  }
  return modification;''')
    return text[:start]+part+text[end:]


def patch_output_v3(text):
    # Each replaced operand is immediately masked to precisely these bits.
    text = replace_once(text, 'LoadFlagsSystemConstant(),\n               dxbc::Src::LU(kSysFlag_ConvertColor0ToGamma << i)',
                        'LoadMaskedFlagsSystemConstant(kSysFlag_ConvertColor0ToGamma << i),\n               dxbc::Src::LU(kSysFlag_ConvertColor0ToGamma << i)')
    for prefix in ('dxbc::Dest::R(system_temp_depth_stencil_, 0b0010)',
                   'dxbc::Dest::R(temp_temp, 1 << temp_temp_component)'):
        text = replace_once(text, prefix+', LoadFlagsSystemConstant(),',
                            prefix+', LoadMaskedFlagsSystemConstant(kSysFlag_DepthFloat24),')
    text = replace_once(text, 'dxbc::Src::LU(kSysFlag_AlphaPassIfLess_Shift),\n              LoadFlagsSystemConstant());',
                        'dxbc::Src::LU(kSysFlag_AlphaPassIfLess_Shift),\n              LoadMaskedFlagsSystemConstant(7u << kSysFlag_AlphaPassIfLess_Shift));')
    return text


def patch_header_v4(text):
    text=patch_header_v3(text)
    text=replace_once(text,'kVersion = 0x20261103;','kVersion = 0x20261104;')
    text=replace_once(text,
        '      uint32_t interpolator_mask : xenos::kMaxInterpolators;\n      uint32_t interpolators_centroid : xenos::kMaxInterpolators;',
        '      uint32_t interpolation_modes : 26;\n      uint32_t native_depth_state : 6;')
    text=replace_once(text,'    explicit Modification(uint64_t modification_value = 0)', '''    static_assert(xenos::kMaxInterpolators == 16);
    void SetPixelInterpolators(uint32_t mask, uint32_t centroid) {
      pixel.interpolation_modes = ch2k8::PackInterpolators(mask, centroid);
    }
    uint32_t GetPixelInterpolatorMask() const {
      return ch2k8::InterpolatorMask(pixel.interpolation_modes);
    }
    uint32_t GetPixelCentroidMask() const {
      return ch2k8::InterpolatorMask(pixel.interpolation_modes, true);
    }
    explicit Modification(uint64_t modification_value = 0)''')
    text=replace_once(text,'modification.pixel.interpolator_mask;', 'modification.GetPixelInterpolatorMask();')
    text=replace_once(text,'''      const auto state = GetDxbcShaderModification().pixel.native_pixel_state;
      if (ch2k8::CanFoldFlags(state, mask)) return dxbc::Src::LU(ch2k8::PixelFlags(state));''',
        '''      const auto modification = GetDxbcShaderModification();
      const auto state = modification.pixel.native_pixel_state;
      const auto depth = modification.pixel.native_depth_state;
      if (ch2k8::CanFoldFlags(state, mask, depth))
        return dxbc::Src::LU(ch2k8::PixelFlags(state, depth));''')
    return text


def patch_pipeline_v4(text):
    text=patch_pipeline_v3(text)
    text=replace_once(text,'REXCVAR_DEFINE_BOOL(ch2k8_native_pixel_state,', '''REXCVAR_DEFINE_BOOL(ch2k8_native_depth_state, true, "GPU/CH2K8",
                    "Specialize exact ROV depth and stencil decisions")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

REXCVAR_DEFINE_BOOL(ch2k8_native_pixel_state,''')
    text=replace_once(text,'''  modification.pixel.interpolator_mask = interpolator_mask;
  modification.pixel.interpolators_centroid =
      interpolator_mask & ~xenos::GetInterpolatorSamplingPattern(''',
        '''  const uint32_t centroid = interpolator_mask & ~xenos::GetInterpolatorSamplingPattern(''')
    site='''                              regs.Get<reg::SQ_INTERPOLATOR_CNTL>().sampling_pattern);
'''
    text=replace_once(text,site,site+'  modification.SetPixelInterpolators(interpolator_mask, centroid);\n')
    text=replace_once(text,'pixel_shader_modification.pixel.interpolator_mask);',
        'pixel_shader_modification.GetPixelInterpolatorMask());')
    site='''        regs[reg::RB_BLENDCONTROL::rt_register_indices[0]] & 0x1FFF1FFFu);
'''
    text=replace_once(text,site,site+'''    // CH2K8 exact depth specialization v1. Match the original alias rule.
    if (REXCVAR_GET(ch2k8_native_depth_state)) {
      const auto depth = regs.Get<reg::RB_DEPTH_INFO>();
      bool enabled = normalized_depth_control.z_enable || normalized_depth_control.stencil_enable;
      if (enabled) {
        const auto mask = draw_util::GetNormalizedColorMask(regs, shader.writes_color_targets());
        for (uint32_t i = 0; i < 4; ++i) {
          const auto color = regs.Get<reg::RB_COLOR_INFO>(reg::RB_COLOR_INFO::rt_register_indices[i]);
          if (depth.depth_base != color.color_base) continue;
          float clamp[4]; uint32_t keep_low, keep_high;
          RenderTargetCache::GetPSIColorFormatInfo(color.color_format, (mask >> (4*i)) & 15u,
              clamp[0], clamp[1], clamp[2], clamp[3], keep_low, keep_high);
          if (keep_low != UINT32_MAX || keep_high != UINT32_MAX) { enabled = false; break; }
        }
      }
      uint32_t depth_flags = 0;
      if (enabled) {
        depth_flags = DxbcShaderTranslator::kSysFlag_ROVDepthStencil;
        depth_flags |= uint32_t(normalized_depth_control.z_enable ? normalized_depth_control.zfunc :
            xenos::CompareFunction::kAlways) << DxbcShaderTranslator::kSysFlag_ROVDepthPassIfLess_Shift;
        if (normalized_depth_control.z_enable && normalized_depth_control.z_write_enable)
          depth_flags |= DxbcShaderTranslator::kSysFlag_ROVDepthWrite;
        if (normalized_depth_control.stencil_enable)
          depth_flags |= DxbcShaderTranslator::kSysFlag_ROVStencilTest;
      }
      modification.pixel.native_depth_state = ch2k8::PackDepthState(depth_flags);
    }
''')
    return text


def patch_output_v4(text):
    text=patch_output_v3(text)
    for flag in ('ROVDepthStencil','ROVDepthWrite','ROVStencilTest'):
        import re
        pattern=r'LoadFlagsSystemConstant\(\)(,\s*dxbc::Src::LU\(kSysFlag_'+flag+r'\))'
        text,count=re.subn(pattern,r'LoadMaskedFlagsSystemConstant(kSysFlag_'+flag+r')\1',text)
        if count!=1:raise ValueError('Unrecognized depth flag site: '+flag)
    text=replace_once(text,'sample_temp_z_dest, sample_temp_z_src, LoadFlagsSystemConstant());',
        '''sample_temp_z_dest, sample_temp_z_src, LoadMaskedFlagsSystemConstant(
        kSysFlag_ROVDepthPassIfLess | kSysFlag_ROVDepthPassIfEqual | kSysFlag_ROVDepthPassIfGreater));''')
    return text


def patch_header_v5(text):
    return replace_once(patch_header_v4(text),'kVersion = 0x20261104;','kVersion = 0x20261105;')


def patch_pipeline_v5(text):
    text=patch_pipeline_v4(text)
    site='          depth_flags |= DxbcShaderTranslator::kSysFlag_ROVStencilTest;\n'
    return replace_once(text,site,site+'        if ((!color.alpha_test_enable || color.alpha_func == xenos::CompareFunction::kAlways) &&\n            !color.alpha_to_mask_enable)\n          depth_flags |= DxbcShaderTranslator::kSysFlag_ROVDepthStencilEarlyWrite;\n')


def patch_header_v6(text):
    text=replace_once(patch_header_v5(text),'kVersion = 0x20261105;','kVersion = 0x20261106;')
    site='      if (ch2k8::PixelStateEnabled(state) && swizzle == dxbc::Src::kXXXX) {'
    return replace_once(text,site,'      // CH2K8 proven RT0 full writes: only components X/Y belong to RT0.\n      if (ch2k8::FullWrite(state) && index == SystemConstants::Index::kEdramRTKeepMask &&\n          offset == offsetof(SystemConstants, edram_rt_keep_mask) && !(swizzle & 0xAAu))\n        return dxbc::Src::LU(0, 0, 0, 0);\n'+site)


def patch_header_v7(text):
    return replace_once(patch_header_v6(text),'kVersion = 0x20261106;','kVersion = 0x20261107;')


def patch_header_v8(text):
    text=replace_once(patch_header_v7(text),'kVersion = 0x20261107;','kVersion = 0x20261108;')
    text=replace_once(text,'#include <rex/graphics/native_pixel_state.h>',
        '#include <rex/graphics/native_pixel_state.h>\n#include <rex/graphics/native_vertex_state.h>')
    return replace_once(text,'Shader::kHostVertexShaderTypeBitCount;\n    } vertex;',
        'Shader::kHostVertexShaderTypeBitCount;\n      uint32_t native_vertex_endian : 3;\n    } vertex;')


def patch_header(text):
    text=replace_once(patch_header_v8(text),'kVersion = 0x20261108;','kVersion = 0x20261109;')
    return replace_once(text,'      uint32_t native_vertex_endian : 3;',
        '      uint32_t native_vertex_endian : 3;\n      uint32_t native_vertex_memory : 2;\n      uint32_t native_index_endian : 3;')


def patch_pipeline_v6_initial(text):
    text=patch_pipeline_v5(text)
    text=replace_once(text,'REXCVAR_DEFINE_BOOL(ch2k8_native_depth_state,', 'REXCVAR_DEFINE_BOOL(ch2k8_native_full_write, false, "GPU/CH2K8",\n                    "Specialize proven full RT0 color writes")\n    .lifecycle(rex::cvar::Lifecycle::kInitOnly);\n\nREXCVAR_DEFINE_BOOL(ch2k8_native_depth_state,')
    return replace_once(text,'regs[reg::RB_BLENDCONTROL::rt_register_indices[0]] & 0x1FFF1FFFu);',
        'regs[reg::RB_BLENDCONTROL::rt_register_indices[0]] & 0x1FFF1FFFu,\n        REXCVAR_GET(ch2k8_native_full_write) &&\n        (draw_util::GetNormalizedColorMask(regs, shader.writes_color_targets()) & 15u) == 15u);')


def patch_pipeline_v7(text):
    text=replace_once(patch_pipeline_v6_initial(text),
        '(draw_util::GetNormalizedColorMask(regs, shader.writes_color_targets()) & 15u) == 15u);',
        'ch2k8::FullWriteEligible(uint32_t(rt0.color_format),\n            draw_util::GetNormalizedColorMask(regs, shader.writes_color_targets())));')
    return text.replace('REXCVAR_DEFINE_BOOL(ch2k8_native_full_write, false,',
                        'REXCVAR_DEFINE_BOOL(ch2k8_native_full_write, true,')


def patch_pipeline_vertex_v1(text):
    text=patch_pipeline_v7(text)
    text=replace_once(text,'REXCVAR_DEFINE_BOOL(ch2k8_native_pixel_state,', '''REXCVAR_DEFINE_BOOL(ch2k8_native_vertex_fetch, false, "GPU/CH2K8",
                    "Specialize common vertex stream byte order per draw")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

REXCVAR_DEFINE_BOOL(ch2k8_native_pixel_state,''')
    start=text.index('DxbcShaderTranslator::Modification PipelineCache::GetCurrentVertexShaderModification(')
    end=text.index('\n}\n',start)
    part=text[start:end]
    part=replace_once(part,'  return modification;', '''  // CH2K8 common vertex endian v1
  if(REXCVAR_GET(ch2k8_native_vertex_fetch)) {
    modification.vertex.native_vertex_endian=ch2k8::SelectVertexEndian(
        shader.constant_register_map().vertex_fetch_bitmap,
        [&](uint32_t index){return uint32_t(regs.GetVertexFetch(index).endian);});
  }
  return modification;''')
    return text[:start]+part+text[end:]


def patch_pipeline_v8(text):
    text=patch_pipeline_vertex_v1(text)
    text=replace_once(text,'REXCVAR_DEFINE_BOOL(ch2k8_native_vertex_fetch,', '''REXCVAR_DEFINE_BOOL(ch2k8_vertex_fetch_compare, false, "GPU/CH2K8",
                    "Diagnostic alternating dynamic/static vertex fetch shader variants")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

REXCVAR_DEFINE_BOOL(ch2k8_native_vertex_fetch,''')
    return replace_once(text,'  if(REXCVAR_GET(ch2k8_native_vertex_fetch)) {',
        '  static thread_local uint32_t native_vertex_selection=0;\n'
        '  if(REXCVAR_GET(ch2k8_native_vertex_fetch) &&\n'
        '     (!REXCVAR_GET(ch2k8_vertex_fetch_compare) || (++native_vertex_selection&1))) {')


def patch_pipeline_native_vertex(text):
    text=patch_pipeline_v8(text)
    text=text.replace('REXCVAR_DEFINE_BOOL(ch2k8_native_vertex_fetch, false,','REXCVAR_DEFINE_BOOL(ch2k8_native_vertex_fetch, true,')
    text=text.replace('Specialize common vertex stream byte order per draw','Specialize vertex byte order, index conversion and read-only memory binding')
    return replace_once(text,'    modification.vertex.native_vertex_endian=ch2k8::SelectVertexEndian(',
        '    modification.vertex.native_vertex_memory=1;\n    modification.vertex.native_vertex_endian=ch2k8::SelectVertexEndian(')


def patch_pipeline(text):
    text = patch_pipeline_native_vertex(text)
    text = replace_once(text, '#include <rex/graphics/flags.h>',
        '#include <rex/graphics/flags.h>\n#include <rex/graphics/native_sync_stats.h>')
    text = replace_once(text, 'REXCVAR_DEFINE_INT32(d3d12_pipeline_creation_threads,',
        'REXCVAR_DEFINE_BOOL(ch2k8_parallel_pipeline_creation, true, "GPU/D3D12",\n'
        '                    "Build translated pipelines on workers before replaying draws")\n'
        '    .lifecycle(rex::cvar::Lifecycle::kInitOnly);\n\n'
        'REXCVAR_DEFINE_INT32(d3d12_pipeline_creation_threads,')
    text = replace_once(text, '  if (use_async) {\n    uint32_t bound_rts =',
        '  // Synchronous mode still translates shaders and resolves root signatures\n'
        '  // here. Only PSO creation is deferred. EndSubmission drains the workers\n'
        '  // before replaying any recorded draw that uses a pipeline handle.\n'
        '  const bool parallel_creation = REXCVAR_GET(ch2k8_parallel_pipeline_creation) &&\n'
        '      !REXCVAR_GET(async_shader_compilation) && !creation_threads_.empty();\n'
        '  if (use_async || parallel_creation) {\n    uint32_t bound_rts =')
    text = replace_once(text,
        '    new_pipeline->pending_vertex_shader = vertex_shader;\n'
        '    new_pipeline->pending_pixel_shader = pixel_shader;',
        '    if (use_async) {\n'
        '      new_pipeline->pending_vertex_shader = vertex_shader;\n'
        '      new_pipeline->pending_pixel_shader = pixel_shader;\n'
        '    }')
    text = replace_once(text, '    CreateQueuedPipelinesOnProcessorThread();\n    // Await creation',
        '    ch2k8::SyncScope pipeline_wait(ch2k8::SyncKind::PipelineWait);\n'
        '    CreateQueuedPipelinesOnProcessorThread();\n    // Await creation')
    return replace_once(text,
        '  if (FAILED(device->CreateGraphicsPipelineState(&state_desc, IID_PPV_ARGS(&state)))) {',
        '  HRESULT creation_result;\n'
        '  {\n'
        '    ch2k8::SyncScope pipeline_creation(ch2k8::SyncKind::PipelineCreation);\n'
        '    creation_result = device->CreateGraphicsPipelineState(&state_desc, IID_PPV_ARGS(&state));\n'
        '  }\n'
        '  if (FAILED(creation_result)) {')


def patch_output(text):
    return replace_once(patch_output_v4(text),
        'a_.OpAnd(sample_temp_x_dest, LoadFlagsSystemConstant(),\n                   dxbc::Src::LU(kSysFlag_ROVDepthStencilEarlyWrite));',
        'a_.OpAnd(sample_temp_x_dest, LoadMaskedFlagsSystemConstant(kSysFlag_ROVDepthStencilEarlyWrite),\n                   dxbc::Src::LU(kSysFlag_ROVDepthStencilEarlyWrite));')


def patch_shader_v7(text):
    text=replace_once(text,'shader_modification.pixel.interpolator_mask = (UINT32_C(1) << xenos::kMaxInterpolators) - 1;',
        'shader_modification.SetPixelInterpolators((UINT32_C(1) << xenos::kMaxInterpolators) - 1, 0);')
    return replace_once(text,'shader_modification.pixel.interpolators_centroid &',
        'shader_modification.GetPixelCentroidMask() &')


def patch_shader(text):
    text=patch_shader_v7(text)
    start=text.index("  {\n    // Swap the vertex index's endianness.")
    end=text.index('  // Remap the index to the needed range',start)
    original=text[start:end]
    if original.count('a_.OpSwitch(endian_src);')!=2:raise ValueError('Unknown vertex index conversion')
    native='''  // CH2K8 static index endian v1
  const uint32_t native_index=GetDxbcShaderModification().vertex.native_index_endian;
  if(native_index) {
    const uint32_t endian=native_index-1;
    const auto swap_dest=dxbc::Dest::R(reg,0b0010);
    const auto swap_src=dxbc::Src::R(reg,dxbc::Src::kYYYY);
    if(endian==1 || endian==2) {
      a_.OpAnd(swap_dest,index_src,dxbc::Src::LU(0x00FF00FF));
      a_.OpUShR(index_dest,index_src,dxbc::Src::LU(8));
      a_.OpAnd(index_dest,index_src,dxbc::Src::LU(0x00FF00FF));
      a_.OpUMAd(index_dest,swap_src,dxbc::Src::LU(256),index_src);
    }
    if(endian==2 || endian==3) {
      a_.OpUShR(swap_dest,index_src,dxbc::Src::LU(16));
      a_.OpBFI(index_dest,dxbc::Src::LU(16),dxbc::Src::LU(16),index_src,swap_src);
    }
    // The original path also initializes GPR0.y when no swap is required.
    if(!uses_register_dynamic_addressing)a_.OpMov(swap_dest,dxbc::Src::LF(0.0f));
  } else {
'''
    return text[:start]+native+original+'  }\n\n'+text[end:]


def prepare_native_shaders(source):
    functions = {
        'include/rex/graphics/pipeline/shader/dxbc_translator.h': patch_header,
        'src/graphics/d3d12/pipeline_cache.cpp': patch_pipeline,
        'src/graphics/pipeline/shader/dxbc_translator_om.cpp': patch_output,
        'src/graphics/pipeline/shader/dxbc_translator.cpp': patch_shader,
    }
    preceding={
        'include/rex/graphics/pipeline/shader/dxbc_translator.h': patch_header_v3,
        'src/graphics/d3d12/pipeline_cache.cpp': patch_pipeline_v3,
        'src/graphics/pipeline/shader/dxbc_translator_om.cpp': patch_output_v3,
        'src/graphics/pipeline/shader/dxbc_translator.cpp': lambda text:text,
    }
    version4={
        'include/rex/graphics/pipeline/shader/dxbc_translator.h':patch_header_v4,
        'src/graphics/d3d12/pipeline_cache.cpp':patch_pipeline_v4,
        'src/graphics/pipeline/shader/dxbc_translator_om.cpp':patch_output_v4,
        'src/graphics/pipeline/shader/dxbc_translator.cpp':patch_shader_v7,
    }
    version5={
        'include/rex/graphics/pipeline/shader/dxbc_translator.h':patch_header_v5,
        'src/graphics/d3d12/pipeline_cache.cpp':patch_pipeline_v5,
        'src/graphics/pipeline/shader/dxbc_translator_om.cpp':patch_output,
        'src/graphics/pipeline/shader/dxbc_translator.cpp':patch_shader_v7,
    }
    initial_v6=dict(version5)
    initial_v6.update({
        'include/rex/graphics/pipeline/shader/dxbc_translator.h':patch_header_v6,
        'src/graphics/d3d12/pipeline_cache.cpp':patch_pipeline_v6_initial,
    })
    version7=dict(functions)
    version7.update({
        'include/rex/graphics/pipeline/shader/dxbc_translator.h':patch_header_v7,
        'src/graphics/d3d12/pipeline_cache.cpp':patch_pipeline_v7,
        'src/graphics/pipeline/shader/dxbc_translator.cpp':patch_shader_v7,
    })
    version8=dict(version7)
    version8.update({
        'include/rex/graphics/pipeline/shader/dxbc_translator.h':patch_header_v8,
        'src/graphics/d3d12/pipeline_cache.cpp':patch_pipeline_v8,
    })
    changes = {}
    for relative, patch in functions.items():
        original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:'+relative], text=True)
        expected = patch(original)
        path = source/relative
        intermediate=patch_pipeline_vertex_v1(original) if relative=='src/graphics/d3d12/pipeline_cache.cpp' else expected
        previous = patch_pipeline_native_vertex(original) if relative=='src/graphics/d3d12/pipeline_cache.cpp' else expected
        geometry_initial=previous.replace('REXCVAR_DEFINE_BOOL(ch2k8_native_vertex_fetch, true,','REXCVAR_DEFINE_BOOL(ch2k8_native_vertex_fetch, false,').replace('Specialize vertex byte order, index conversion and read-only memory binding','Specialize common vertex stream byte order per draw')
        if path.read_text() not in (original, preceding[relative](original), version4[relative](original), version5[relative](original), initial_v6[relative](original), version7[relative](original), version8[relative](original), intermediate, geometry_initial, previous.replace('REXCVAR_DEFINE_BOOL(ch2k8_native_full_write, true,', 'REXCVAR_DEFINE_BOOL(ch2k8_native_full_write, false,'), previous.replace('REXCVAR_DEFINE_BOOL(ch2k8_native_depth_state, true,', 'REXCVAR_DEFINE_BOOL(ch2k8_native_depth_state, false,'), previous, expected):
            raise ValueError('Unreviewed shader SDK changes: '+relative)
        changes[path] = expected
    for path, expected in changes.items():
        if path.read_text() != expected:
            path.write_text(expected, encoding='utf-8', newline='\n')
    destination = source/'include/rex/graphics/native_pixel_state.h'
    data = (ROOT/'port/sdk_patches/native_pixel_state.h').read_bytes()
    if not destination.exists() or destination.read_bytes() != data:
        destination.write_bytes(data)
    destination=source/'include/rex/graphics/native_vertex_state.h'
    data=(ROOT/'port/sdk_patches/native_vertex_state.h').read_bytes()
    if not destination.exists() or destination.read_bytes()!=data:destination.write_bytes(data)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    prepare_native_shaders(parser.parse_args().source)
