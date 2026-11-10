# ch2k8 - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake (written by `rexglue codegen`).

cmake_minimum_required(VERSION 3.25)
project(ch2k8 VERSION 0.0.1 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
include(cmake/Ch2k8BuildOptions.cmake)

find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_library(ch2k8_asset_codec SHARED ../tools/asset_codec.cpp)
add_executable(ch2k8_tools ../tools/ch2k8_tools.cpp ../tools/asset_codec.cpp)
target_sources(ch2k8_tools PRIVATE third_party/miniz/miniz.c)
target_compile_definitions(ch2k8_tools PRIVATE MINIZ_NO_ARCHIVE_APIS MINIZ_NO_DEFLATE_APIS MINIZ_NO_ZLIB_APIS MINIZ_NO_STDIO)
target_link_libraries(ch2k8_tools PRIVATE bcrypt)
target_compile_options(ch2k8_tools PRIVATE $<$<CXX_COMPILER_ID:Clang>:-O2>)
if(WIN32)
    add_executable(ch2k8_assets_check ../tools/native_assets_check.cpp)
    target_compile_definitions(ch2k8_assets_check PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
    target_link_libraries(ch2k8_assets_check PRIVATE d3d12 dxgi)
endif()

# Keep the generated SDK boilerplate intact. Include a build-directory copy
# whose codegen command preserves the manifest timestamp after a no-op rewrite.
# Otherwise the pinned SDK's final sdk_version rewrite makes Ninja dirty again.
set(CH2K8_SDK_CMAKE "${CMAKE_CURRENT_SOURCE_DIR}/generated/rexglue.cmake")
file(READ "${CH2K8_SDK_CMAKE}" CH2K8_SDK_CMAKE_CONTENT)
set(CH2K8_ORIGINAL_CODEGEN
    "COMMAND $<TARGET_FILE:rex::rexglue> codegen \${CMAKE_CURRENT_SOURCE_DIR}/ch2k8_manifest.toml")
string(FIND "${CH2K8_SDK_CMAKE_CONTENT}" "${CH2K8_ORIGINAL_CODEGEN}" CH2K8_COMMAND_OFFSET)
if(CH2K8_COMMAND_OFFSET EQUAL -1)
    message(FATAL_ERROR "Unrecognized SDK codegen command; use the documented pinned SDK")
endif()
string(REPLACE "${CH2K8_ORIGINAL_CODEGEN}"
    "COMMAND \"${Python3_EXECUTABLE}\" \"${CMAKE_CURRENT_SOURCE_DIR}/../tools/run_codegen.py\" $<TARGET_FILE:rex::rexglue> \"${CMAKE_CURRENT_SOURCE_DIR}/ch2k8_manifest.toml\" \"${CMAKE_CURRENT_SOURCE_DIR}/generated/default\""
    CH2K8_SDK_CMAKE_CONTENT "${CH2K8_SDK_CMAKE_CONTENT}")
file(CONFIGURE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/rexglue.cmake"
    CONTENT "${CH2K8_SDK_CMAKE_CONTENT}" @ONLY)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CH2K8_SDK_CMAKE}")
include("${CMAKE_CURRENT_BINARY_DIR}/rexglue.cmake")
add_custom_command(
    OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/codegen.build.stamp"
    APPEND DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/run_codegen.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/fix_codegen.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/optimize_codegen.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/prove_vector_store_ranges.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/geometry_batch_codegen.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/geometry_ram_codegen.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/geometry_input_codegen.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/gpu_wait_codegen.py")
set(CH2K8_GAME_SOURCE "" CACHE FILEPATH "Xbox ISO or extracted disc directory for folder import")
set(CH2K8_ASSET_DESTINATION "${CMAKE_CURRENT_SOURCE_DIR}/out/folder-game" CACHE PATH "New folder installation directory")
if(CH2K8_GAME_SOURCE)
    add_custom_target(ch2k8_import_assets
        COMMAND $<TARGET_FILE:ch2k8_tools> import "${CH2K8_GAME_SOURCE}" "${CH2K8_ASSET_DESTINATION}"
        DEPENDS ch2k8_tools
        USES_TERMINAL VERBATIM)
endif()
if(WIN32)
    add_executable(ch2k8_vfs_check ../tools/loose_vfs_check.cpp src/loose_device.cpp)
    target_link_libraries(ch2k8_vfs_check PRIVATE rex::runtime)
endif()

option(CH2K8_REQUIRE_VULKAN "Require a Vulkan-capable installed SDK" OFF)
if(CH2K8_REQUIRE_VULKAN)
    get_target_property(CH2K8_SDK_DEFINITIONS rex::runtime INTERFACE_COMPILE_DEFINITIONS)
    if(NOT "REX_HAS_VULKAN=1" IN_LIST CH2K8_SDK_DEFINITIONS)
        message(FATAL_ERROR "Vulkan SDK required. Run tools/build_vulkan_sdk.ps1 first; the default Windows SDK is D3D12-only.")
    endif()
endif()

set(CH2K8_SOURCES
    src/main.cpp
    src/frame_timing.cpp
    src/output_capture.cpp
    src/hot_functions.cpp
    src/native_gpu_wait.cpp
    src/loose_device.cpp
)

if(WIN32)
    add_executable(ch2k8 WIN32 ${CH2K8_SOURCES})
else()
    add_executable(ch2k8 ${CH2K8_SOURCES})
endif()

rexglue_setup_target(ch2k8 GPU_PLUGINS xenos)
if(WIN32)
    # The GPU plugin is loaded dynamically, so an SDK DLL change need not change
    # an import library. Relink to run the SDK's POST_BUILD DLL staging commands.
    set_property(TARGET ch2k8 APPEND PROPERTY LINK_DEPENDS
        "$<TARGET_FILE:rex::gpu-xenos>" "$<TARGET_FILE:rex::runtime>")
endif()
# Public Vulkan provider headers reference the RenderDoc application API; the
# pinned SDK does not install that dependency's header. Use our licensed copy.
target_include_directories(ch2k8 PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/third_party")
target_compile_definitions(ch2k8 PRIVATE CH2K8_VERSION="${PROJECT_VERSION}")
get_target_property(CH2K8_RUNTIME_INCLUDES rex::runtime INTERFACE_INCLUDE_DIRECTORIES)
set(CH2K8_NATIVE_DDS_AVAILABLE 0)
foreach(CH2K8_INCLUDE IN LISTS CH2K8_RUNTIME_INCLUDES)
    if(EXISTS "${CH2K8_INCLUDE}/rex/graphics/native_dds.h")
        set(CH2K8_NATIVE_DDS_AVAILABLE 1)
    endif()
endforeach()
target_compile_definitions(ch2k8 PRIVATE CH2K8_HAS_NATIVE_DDS=${CH2K8_NATIVE_DDS_AVAILABLE})
if(WIN32)
    # Preserve the generated code's line tables in a PDB for startup debugging.
    target_link_options(ch2k8 PRIVATE "LINKER:/DEBUG:FULL" "LINKER:/INCREMENTAL:NO")
endif()

# SDK 0.10.0.24 emits a 32-bit cast before a 44-bit arithmetic shift for
# vupkd3d128's packed signed 20-bit lanes. Correct only those exact expressions
# after codegen and before compilation; never hand-edit generated sources.
if(TARGET ch2k8_recomp)
    # The pinned SDK rewrites sdk_version in the manifest after writing its
    # build stamp, even if the text is unchanged. Stamp completion last so the
    # manifest does not make codegen (and every object) dirty on every build.
    add_custom_command(
        OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/codegen.build.stamp"
        APPEND
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/../tools/run_codegen.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/../tools/fix_codegen.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/../tools/optimize_codegen.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/../tools/prove_vector_store_ranges.py"
        COMMAND "${CMAKE_COMMAND}" -E touch
                "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/codegen.build.stamp"
    )
    target_compile_options(ch2k8_recomp PRIVATE
        $<$<CXX_COMPILER_ID:Clang,AppleClang>:-Werror=shift-count-overflow>)
endif()

# Keep release optimization explicit even with an empty CMAKE_CXX_FLAGS_RELEASE.
# No fast-math, host-only ISA extensions or changed guest arithmetic are enabled.
foreach(CH2K8_BUILD_TARGET IN ITEMS ch2k8 ch2k8_recomp ch2k8_asset_codec ch2k8_tools ch2k8_assets_check ch2k8_vfs_check)
    if(TARGET ${CH2K8_BUILD_TARGET})
        ch2k8_apply_build_options(${CH2K8_BUILD_TARGET})
    endif()
endforeach()
