"""Apply reviewed CH2K8 fixes to the exact pinned source SDK, never game code."""
import argparse
import subprocess
from pathlib import Path
from prepare_native_gpu_sdk import prepare_native_gpu
from prepare_native_shader_sdk import prepare_native_shaders
from prepare_native_sync_sdk import prepare_sync
from prepare_native_assets_sdk import prepare_native_assets
from prepare_native_pcm_sdk import prepare_native_pcm
from prepare_content_sdk import prepare_content
from prepare_native_vertex_sdk import prepare_native_vertex
from prepare_native_presenter_sdk import prepare_native_presenter
from prepare_portable_sdk import prepare_portable
from prepare_display_sdk import prepare_display

PIN = 'bd833a2ab69d305f99ddf57418fc38ffec8af93d'


def prepare(source):
    revision = subprocess.check_output(
        ['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PIN:
        raise ValueError(f'Expected pinned SDK {PIN}, got {revision}')
    prepare_native_gpu(source)
    prepare_native_shaders(source)
    prepare_native_vertex(source)
    prepare_native_presenter(source)
    prepare_sync(source)
    prepare_native_assets(source)
    prepare_native_pcm(source)
    prepare_content(source)
    prepare_portable(source)
    prepare_display(source)
    # Windows Git may check out symlinks as small text files. Materialize only
    # libmspack's tracked file links, using the target recorded in Git and
    # requiring both ends to remain inside that dependency.
    dependency = (source / 'thirdparty/libmspack').resolve()
    entries = subprocess.check_output(
        ['git', '-C', str(dependency), 'ls-files', '-s'], text=True)
    for entry in entries.splitlines():
        metadata, name = entry.split('\t', 1)
        if not metadata.startswith('120000 '):
            continue
        destination = dependency / name
        if destination.is_symlink():
            continue
        target_name = subprocess.check_output(
            ['git', '-C', str(dependency), 'show', f'HEAD:{name}'], text=True).strip()
        target = (destination.parent / target_name).resolve()
        if not target.is_relative_to(dependency) or not target.is_file():
            raise ValueError(f'Unsafe or missing dependency symlink target: {name}')
        if destination.read_bytes() != target.read_bytes():
            destination.write_bytes(target.read_bytes())
    path = source / 'src/ui/window_sdl.cpp'
    original = ('SDL_GetClosestFullscreenDisplayMode(display, width, height, '
                '0.0f, true, &mode)')
    corrected = ('SDL_GetClosestFullscreenDisplayMode(display, width, height, '
                 'float(REXCVAR_GET(video_mode_refresh_rate)), true, &mode)')
    text = path.read_text(encoding='utf-8')
    if corrected in text and original not in text:
        return
    if text.count(original) != 1:
        raise ValueError('Unrecognized fullscreen mode selector; refusing to patch')
    path.write_text(text.replace(original, corrected), encoding='utf-8', newline='\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    prepare(parser.parse_args().source)
