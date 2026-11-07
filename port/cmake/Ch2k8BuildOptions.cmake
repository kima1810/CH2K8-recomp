# Do not rely on CMake's global Release defaults: the pinned SDK/toolchain may
# leave them empty. Apply these to both generated game code and native glue.
function(ch2k8_apply_build_options target_name)
    target_compile_options(${target_name} PRIVATE
        $<$<AND:$<CONFIG:Release,RelWithDebInfo>,$<CXX_COMPILER_ID:Clang,AppleClang,GNU>>:-O2>
        $<$<AND:$<CONFIG:MinSizeRel>,$<CXX_COMPILER_ID:Clang,AppleClang,GNU>>:-Os>
        $<$<AND:$<CONFIG:Release,RelWithDebInfo,MinSizeRel>,$<CXX_COMPILER_ID:MSVC>>:/O2>
        $<$<CXX_COMPILER_ID:Clang,AppleClang,GNU>:-fno-strict-aliasing>
        $<$<CXX_COMPILER_ID:Clang,AppleClang,GNU>:-fwrapv>
        $<$<CXX_COMPILER_ID:Clang,AppleClang>:-ffp-model=strict>
        $<$<CXX_COMPILER_ID:GNU>:-frounding-math>
        $<$<CXX_COMPILER_ID:GNU>:-ffp-contract=off>
        $<$<CXX_COMPILER_ID:MSVC>:/fp:strict>
    )
    target_compile_definitions(${target_name} PRIVATE
        $<$<CONFIG:Release,RelWithDebInfo,MinSizeRel>:NDEBUG>)
endfunction()
