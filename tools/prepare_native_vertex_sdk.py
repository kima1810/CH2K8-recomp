"""Exact common-endian specialization of geometry vertex fetches."""
from pathlib import Path
import subprocess
from prepare_native_gpu_sdk import replace_once


def patch_vertex_fetch_v1(text):
    marker='// CH2K8 static vertex endian v1'
    if marker in text:return text
    start=text.index('  // - Endian swap the words.')
    end=text.index('  // - Unpack the format.',start)
    original=text[start:end]
    if original.count('a_.OpSwitch(endian_src);')!=2:
        raise ValueError('Unrecognized vertex endian conversion')
    specialized='''  // CH2K8 static vertex endian v1
  const uint32_t native_endian=GetDxbcShaderModification().vertex.native_vertex_endian;
  if(native_endian) {
    const uint32_t endian=native_endian-1;
    if(endian) {
      const uint32_t swap_temp=PushSystemTemp();
      const auto temp_dest=dxbc::Dest::R(swap_temp,needed_words);
      const auto temp_src=dxbc::Src::R(swap_temp);
      const auto result_dest=dxbc::Dest::R(system_temp_result_,needed_words);
      if(endian==1 || endian==2) {
        a_.OpAnd(temp_dest,result_src,dxbc::Src::LU(0x00FF00FF));
        a_.OpUShR(result_dest,result_src,dxbc::Src::LU(8));
        a_.OpAnd(result_dest,result_src,dxbc::Src::LU(0x00FF00FF));
        a_.OpUMAd(result_dest,temp_src,dxbc::Src::LU(256),result_src);
      }
      if(endian==2 || endian==3) {
        a_.OpUShR(temp_dest,result_src,dxbc::Src::LU(16));
        a_.OpBFI(result_dest,dxbc::Src::LU(16),dxbc::Src::LU(16),result_src,temp_src);
      }
      PopSystemTemp();
    }
  } else {
'''
    return text[:start]+specialized+original+'  }\n\n'+text[end:]


def patch_vertex_fetch(text):
    text=patch_vertex_fetch_v1(text)
    marker='// CH2K8 static vertex memory binding v1'
    if marker in text:return text
    site='  a_.OpAnd(dxbc::Dest::R(system_temp_result_, 0b0001), LoadFlagsSystemConstant(),\n           dxbc::Src::LU(kSysFlag_SharedMemoryIsUAV));\n  a_.OpIf(false, dxbc::Src::R(system_temp_result_, dxbc::Src::kXXXX));'
    text=replace_once(text,site,'''  // CH2K8 static vertex memory binding v1
  const uint32_t native_memory=GetDxbcShaderModification().vertex.native_vertex_memory;
  if(!native_memory) {
'''+site+'\n  }')
    start=text.index(marker)
    end=text.index('  dxbc::Src result_src',start)
    part=text[start:end]
    part=replace_once(part,'    if (i) {','    if(native_memory && i!=native_memory-1)continue;\n    if (!native_memory && i) {')
    part=replace_once(part,'  a_.OpEndIf();','  if(!native_memory)a_.OpEndIf();')
    return text[:start]+part+text[end:]


def prepare_native_vertex(source):
    relative='src/graphics/pipeline/shader/dxbc_translator_fetch.cpp'
    original=subprocess.check_output(['git','-C',str(source),'show','HEAD:'+relative],text=True)
    expected=patch_vertex_fetch(original)
    path=source/relative
    if path.read_text(encoding='utf-8') not in (original,patch_vertex_fetch_v1(original),expected):
        raise ValueError('Unreviewed native vertex shader source')
    if path.read_text(encoding='utf-8')!=expected:
        path.write_text(expected,encoding='utf-8',newline='\n')
