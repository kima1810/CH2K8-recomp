"""Version-checked native constant-state caching for the pinned Xenos backends."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unrecognized native-constant patch site: '+old[:100])
    return text.replace(old, new, 1)


def patch_backend_constants(text, backend):
    marker = '// CH2K8 native constant cache v1'
    if marker in text:
        text = patch_vulkan_counters(text) if backend == 'vulkan' else text
        return patch_changed_usage(text)
    cls = 'D3D12CommandProcessor' if backend == 'd3d12' else 'VulkanCommandProcessor'
    text = replace_once(text, '#include <rex/graphics/flags.h>',
                        '#include <rex/graphics/flags.h>\n#include <rex/graphics/native_constants.h>\n'+marker)
    signature = f'void {cls}::WriteRegister(uint32_t index, uint32_t value) {{\n'
    text = replace_once(text, signature, signature+
                        '  if (ch2k8::SkipConstantWrite(register_file_->values, index, value)) return;\n')
    start = text.index(f'void {cls}::WriteRegistersFromMem(')
    end = text.index('\n}', start)
    body = text[start:end]
    at = body.index('{\n')+2
    body = body[:at]+'  if (ch2k8::SkipConstantRange(register_file_->values, start_index, base, num_registers)) return;\n'+body[at:]
    text = text[:start]+body+text[end:]
    swap = text.index(f'void {cls}::IssueSwap(')
    at = text.index('{\n', swap)+2
    text = text[:at]+f'  ch2k8::FlushConstantStats("{backend}");\n'+text[at:]
    if backend == 'd3d12':
        for condition, kind in [('!cbuffer_binding_system_.up_to_date', 'System'),
                                ('!cbuffer_binding_float_vertex_.up_to_date', 'Float'),
                                ('!cbuffer_binding_float_pixel_.up_to_date', 'Float'),
                                ('!cbuffer_binding_bool_loop_.up_to_date', 'Bool')]:
            original = f'  if ({condition}) {{\n'
            text = replace_once(text, original, original+f'    ch2k8::RecordConstantUpload(ch2k8::Upload::{kind});\n')
    text = patch_vulkan_counters(text) if backend == 'vulkan' else text
    return patch_changed_usage(text)


def patch_backend_v3(text, backend):
    text = patch_backend_constants(text, backend)
    if backend != 'd3d12' or '// CH2K8 validate specialized pixel state v3' in text:
        return text
    site = '''                             used_texture_mask, normalized_depth_control, normalized_color_mask);

  // Update constant buffers, descriptors and root parameters.'''
    return replace_once(text, site, '''                             used_texture_mask, normalized_depth_control, normalized_color_mask);

  // CH2K8 validate specialized pixel state v3
  const auto native_state = pixel_shader_modification.pixel.native_pixel_state;
  if (pixel_shader && ch2k8::PixelStateEnabled(native_state) &&
      (ch2k8::PixelFlags(native_state) != (system_constants_.flags & ch2k8::kPixelFlagMask) ||
       ch2k8::SampleLog2(native_state, 0) != system_constants_.sample_count_log2[0] ||
       ch2k8::SampleLog2(native_state, 1) != system_constants_.sample_count_log2[1] ||
       ((system_constants_.edram_rt_keep_mask[0][0] != UINT32_MAX ||
         system_constants_.edram_rt_keep_mask[0][1] != UINT32_MAX) &&
        (ch2k8::ColorFormat(native_state) != (system_constants_.edram_rt_format_flags[0] & 15u) ||
         (ch2k8::HasBlend(native_state) &&
          system_constants_.edram_rt_blend_factors_ops[0] != ch2k8::BlendControl(native_state)))))) {
    REXLOG_ERROR("CH2K8 specialized pixel state mismatch");
    return false;
  }

  // Update constant buffers, descriptors and root parameters.''')


def patch_backend_v5(text, backend):
    if backend=='d3d12' and '// CH2K8 validate specialized pixel state v4' in text:
        return patch_backend_constants(text, backend)
    text=patch_backend_v3(text, backend)
    if backend!='d3d12':return text
    if '// CH2K8 validate specialized pixel state v4' in text:return text
    text=replace_once(text,'// CH2K8 validate specialized pixel state v3',
        '// CH2K8 validate specialized pixel state v4')
    text=replace_once(text,'  const auto native_state = pixel_shader_modification.pixel.native_pixel_state;',
        '''  const auto native_state = pixel_shader_modification.pixel.native_pixel_state;
  const auto native_depth = pixel_shader_modification.pixel.native_depth_state;
  const auto native_flag_mask = ch2k8::kPixelFlagMask | ch2k8::DepthFlagMask(native_depth);''')
    return replace_once(text,
        'ch2k8::PixelFlags(native_state) != (system_constants_.flags & ch2k8::kPixelFlagMask)',
        'ch2k8::PixelFlags(native_state, native_depth) != (system_constants_.flags & native_flag_mask)')


def patch_backend_full_write(text,backend):
    text=patch_backend_v5(text,backend)
    if backend!='d3d12' or '// CH2K8 validate full writes v1' in text:return text
    text=replace_once(text,'// CH2K8 validate specialized pixel state v4',
        '// CH2K8 validate specialized pixel state v4\n  // CH2K8 validate full writes v1')
    return replace_once(text,'(ch2k8::PixelFlags(native_state, native_depth) !=',
        '((ch2k8::FullWrite(native_state) && (system_constants_.edram_rt_keep_mask[0][0] ||\n       system_constants_.edram_rt_keep_mask[0][1])) ||\n      ch2k8::PixelFlags(native_state, native_depth) !=')


def patch_backend_geometry_v1(text,backend):
    text=patch_backend_full_write(text,backend)
    if backend!='d3d12' or '// CH2K8 draw geometry state v1' in text:return text
    site='          *vertex_shader, primitive_processing_result.host_vertex_shader_type, interpolator_mask);'
    text=replace_once(text,site,site+'''
  // CH2K8 draw geometry state v1: share the decisions used for binding/upload.
  if(vertex_shader_modification.vertex.native_vertex_memory) {
    vertex_shader_modification.vertex.native_vertex_memory=memexport_used?2:1;
    vertex_shader_modification.vertex.native_index_endian=
        uint32_t(primitive_processing_result.host_shader_index_endian)+1;
  }''')
    site='  // Update constant buffers, descriptors and root parameters.'
    return replace_once(text,site,'''  // Validate against the system constants consumed by the original shader.
  if(vertex_shader_modification.vertex.native_vertex_memory &&
     ((vertex_shader_modification.vertex.native_vertex_memory==2) !=
          bool(system_constants_.flags & DxbcShaderTranslator::kSysFlag_SharedMemoryIsUAV) ||
      vertex_shader_modification.vertex.native_index_endian-1 != uint32_t(system_constants_.vertex_index_endian))) {
    REXLOG_ERROR("CH2K8 specialized geometry state mismatch");
    return false;
  }

'''+site)


def patch_backend(text,backend):
    text=patch_backend_geometry_v1(text,backend)
    if backend!='d3d12' or '// CH2K8 memexport geometry fallback v1' in text:return text
    return replace_once(text,'''    vertex_shader_modification.vertex.native_vertex_memory=memexport_used?2:1;
    vertex_shader_modification.vertex.native_index_endian=
        uint32_t(primitive_processing_result.host_shader_index_endian)+1;''', '''    // CH2K8 memexport geometry fallback v1: retain the original UAV path.
    if(memexport_used) {
      vertex_shader_modification.vertex.native_vertex_memory=0;
      vertex_shader_modification.vertex.native_vertex_endian=0;
      vertex_shader_modification.vertex.native_index_endian=0;
    } else {
      vertex_shader_modification.vertex.native_vertex_memory=1;
      vertex_shader_modification.vertex.native_index_endian=
          uint32_t(primitive_processing_result.host_shader_index_endian)+1;
    }''')


def patch_changed_usage(text):
    marker = '// CH2K8 changed constant usage v1'
    if marker in text:
        return text
    original = '  auto range_has_any_constant_usage = [](const uint64_t* usage_map, uint32_t first_constant,'
    inserted = '''  // CH2K8 changed constant usage v1
  uint64_t native_changed_constants[8]{};
  const bool native_float_changes = REXCVAR_GET(ch2k8_native_constants) &&
      Ch2k8RangeWithin(start_index, num_registers, XE_GPU_REG_SHADER_CONSTANT_000_X,
                        XE_GPU_REG_SHADER_CONSTANT_511_W);
  if (native_float_changes) {
    Ch2k8ChangedConstantVectors(register_file_->values + start_index, base,
        start_index-XE_GPU_REG_SHADER_CONSTANT_000_X, num_registers, native_changed_constants);
  }
  auto range_has_any_constant_usage = [&](const uint64_t* usage_map, uint32_t first_constant,'''
    text = replace_once(text, original, inserted)
    original = '    if (first_constant > last_constant) {\n      return false;\n    }\n'
    added = original+'''    if (native_float_changes) {
      const unsigned bank = usage_map == current_float_constant_map_pixel_ ? 4 : 0;
      return Ch2k8ChangedConstantsUsed(usage_map, native_changed_constants+bank,
                                        first_constant, last_constant);
    }
'''
    return replace_once(text, original, added)


def patch_vulkan_counters(text):
    marker = '// CH2K8 Vulkan constant upload counters v1'
    if marker in text:
        return text
    for constant, kind in [('System', 'System'), ('FloatVertex', 'Float'),
                           ('FloatPixel', 'Float'), ('BoolLoop', 'Bool')]:
        old = ('    if (!(current_constant_buffers_up_to_date_ &\n'
               f'          (UINT32_C(1) << SpirvShaderTranslator::kConstantBuffer{constant}))) {{\n')
        text = replace_once(text, old, old+f'      ch2k8::RecordConstantUpload(ch2k8::Upload::{kind});\n')
    return text.replace('// CH2K8 native constant cache v1', '// CH2K8 native constant cache v1\n'+marker, 1)


def patch_common(text):
    original = 'REXCVAR_DEFINE_BOOL(vsync, true, "GPU", "Enable vertical sync");'
    marker = '// CH2K8 native constant flags v1'
    if marker not in text:
        text = replace_once(text, original, original+'\n'+marker+'''
REXCVAR_DEFINE_BOOL(ch2k8_native_constants, true, "GPU/CH2K8",
                    "Skip bit-identical float/bool/loop shader constant updates")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_BOOL(ch2k8_gpu_stats, false, "GPU/CH2K8",
                    "Opt-in one-second native shader constant statistics")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
''')
    packet_marker = '// CH2K8 native constant packets v1'
    if packet_marker not in text and '// CH2K8 native constant packets v2' not in text:
        text = replace_once(text, '#include <rex/graphics/flags.h>',
                            '#include <rex/graphics/flags.h>\n#include <rex/graphics/native_constants.h>')
        text = replace_once(text, marker, marker+'''
REXCVAR_DEFINE_BOOL(ch2k8_native_packets, true, "GPU/CH2K8",
                    "Bulk-decode sequential pure shader constant packets")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
''')
        original = '  uint32_t write_one_reg = (packet >> 15) & 0x1;\n'
        text = replace_once(text, original, original+'''  // CH2K8 native constant packets v1
  if (REXCVAR_GET(ch2k8_native_packets) && !write_one_reg &&
      !(reader->read_offset() & 3) && !(reader->capacity() & 3) &&
      ch2k8::IsConstantRange(base_index, count)) {
    ch2k8::RecordBulkPacket(count);
    WriteRegisterRangeFromRing(reader, base_index, count);
    return true;
  }
''')
    packet_v2 = '// CH2K8 native constant packets v2'
    if packet_v2 not in text:
        text = replace_once(text, '// CH2K8 native constant packets v1', packet_v2)
        old = '''  if (REXCVAR_GET(ch2k8_native_packets) && !write_one_reg &&
      !(reader->read_offset() & 3) && !(reader->capacity() & 3) &&
      ch2k8::IsConstantRange(base_index, count)) {'''
        new = '''  const bool native_eligible = !write_one_reg &&
      !(reader->read_offset() & 3) && !(reader->capacity() & 3) &&
      ch2k8::IsConstantRange(base_index, count);
  const bool native_bulk = native_eligible && ch2k8::ChooseNativePacket();
  ch2k8::PacketScope native_scope(native_eligible, native_bulk, count);
  if (native_bulk) {'''
        text = replace_once(text, old, new)
        text = replace_once(text, '// CH2K8 native constant flags v1', '''// CH2K8 native constant flags v1
REXCVAR_DEFINE_BOOL(ch2k8_packet_compare, false, "GPU/CH2K8",
                    "Randomly interleave native and per-word constant packets for measurement")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
''')
    return text


def prepare_native_gpu(source):
    import subprocess
    paths = {}
    for relative in ('src/graphics/command_processor.cpp',
                     'src/graphics/d3d12/command_processor.cpp',
                     'src/graphics/vulkan/command_processor.cpp'):
        path = source/relative
        original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:'+relative], text=True)
        if '/d3d12/' in relative:
            expected = patch_backend(original, 'd3d12')
        elif '/vulkan/' in relative:
            expected = patch_backend(original, 'vulkan')
        else:
            expected = patch_common(original)
        current = path.read_text(encoding='utf-8')
        previous = patch_backend_constants(original, 'd3d12') if '/d3d12/' in relative else expected
        preceding = patch_backend_v3(original, 'd3d12') if '/d3d12/' in relative else expected
        from prepare_native_sync_sdk import patch_sync, patch_sync_v1, patch_sync_attribution
        with_sync = patch_sync(expected, 'common' if '/d3d12/' not in relative else 'd3d12') if '/vulkan/' not in relative else expected
        if ('/vulkan/' not in relative and current == patch_sync_attribution(expected,'common' if '/d3d12/' not in relative else 'd3d12')) or current == with_sync or ('/vulkan/' not in relative and current == patch_sync_v1(expected, 'common' if '/d3d12/' not in relative else 'd3d12')): expected = current
        published = patch_sync(patch_backend_v5(original,'d3d12'),'d3d12') if '/d3d12/' in relative else expected
        if current == published: expected = with_sync
        legacy=patch_sync(patch_backend_full_write(original,'d3d12'),'d3d12') if '/d3d12/' in relative else expected
        geometry_legacy=patch_sync(patch_backend_geometry_v1(original,'d3d12'),'d3d12') if '/d3d12/' in relative else expected
        pre_wait_variants = ()
        if '/d3d12/' in relative:
            pre_wait_variants = tuple(patch_sync_attribution(patch(original, 'd3d12'), 'd3d12')
                for patch in (patch_backend_v5, patch_backend_full_write, patch_backend_geometry_v1))
        if current not in (original, previous, preceding, published, legacy, geometry_legacy,
                           expected, *pre_wait_variants):
            raise ValueError('Unreviewed local GPU SDK changes: '+relative)
        paths[path] = expected
    # Validate every insertion before writing any backend source.
    for path, text in paths.items():
        if path.read_text(encoding='utf-8') != text:
            path.write_text(text, encoding='utf-8', newline='\n')
    for name, template in [('native_constants.h', ROOT/'port/sdk_patches/native_constants.h'),
                           ('native_constant_compare.h', ROOT/'port/src/native_constant_compare.h')]:
        path = source/'include/rex/graphics'/name
        data = template.read_bytes()
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
