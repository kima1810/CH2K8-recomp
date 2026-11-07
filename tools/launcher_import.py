"""Developer reference implementation for native ISO-import regression tests.

The distributed launcher invokes ch2k8_tools.exe; this module is not shipped.
"""
import argparse
import contextlib
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path


SUPPORTED_XEX_SHA256 = '71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36'


def inspect_iso(image, cancel_file=None):
    from xbox_disc_source import XboxISO
    from ch2k8_archive import open_archive
    image = Path(image).resolve(strict=True)
    source = XboxISO(image)
    digest = hashlib.sha256()
    with (source/'default.xex').open('rb') as stream:
        while chunk := stream.read(8 << 20):
            if cancel_file and Path(cancel_file).exists():
                raise InterruptedError('ISO import cancelled')
            digest.update(chunk)
    if digest.hexdigest() != SUPPORTED_XEX_SHA256:
        raise ValueError('Unsupported default.xex: use the original USA Xbox 360 College Hoops 2K8 ISO. Other games/revisions are not compatible with this recompilation.')
    archive = open_archive(source)
    for part in archive.parts:
        member = source/part.name
        if not member.is_file():
            raise ValueError(f'Incomplete Xbox ISO: missing archive part {part.name}')
        if source.members[part.name.casefold()][1] < part.units * 2048:
            raise ValueError(f'Truncated Xbox ISO archive part {part.name}')
    return dict(image_bytes=image.stat().st_size, xex_sha256=digest.hexdigest(),
                archive_parts=len(archive.parts), archive_entries=len(archive.entries),
                archive_bytes=archive.total, supported=True)


def import_iso(image, output, progress_file=None, cancel_file=None):
    if sys.version_info < (3,11):raise ValueError('ISO import requires Python 3.11 or newer')
    from loose_assets import import_disc
    image=Path(image).resolve(strict=True)
    output=Path(output).absolute()
    if not image.is_file() or image.suffix.lower()!='.iso':
        raise ValueError('Choose an Xbox 360 .iso file')
    if output.exists():raise ValueError('Installation folder already exists; select it in the launcher or choose a new destination')
    if not output.parent.is_dir():raise ValueError('Choose an existing parent folder for the installation')
    last_update=0
    def progress(done=0,total=0,message=None):
        nonlocal last_update
        if cancel_file and Path(cancel_file).exists():raise InterruptedError('ISO import cancelled')
        now=time.monotonic()
        if progress_file and (message or done==total or now-last_update>=0.25):
            path=Path(progress_file)
            temporary=path.with_suffix('.tmp')
            label=message or ('Preparing loose resource maps...' if total and done==total else f'Extracting assets: {done}/{total}')
            temporary.write_text(json.dumps(dict(done=done,total=total,message=label)),encoding='utf-8')
            temporary.replace(path)
            last_update=now
    progress(message='Checking ISO identity, archive parts and available disk space...')
    validation = inspect_iso(image, cancel_file)
    # A lower bound, not a promise that decoded resources fit this estimate.
    minimum = validation['archive_bytes'] + (1 << 30)
    if shutil.disk_usage(output.parent).free < minimum:
        raise OSError(f'Not enough disk space: at least {minimum / (1 << 30):.1f} GiB free is required before import; decoded assets may need more.')
    progress(message='Reading Xbox ISO and preparing loose assets...')
    # Keep incomplete output separate. Only our own temporary directory is ever
    # removed; an existing installation is never overwritten or cleaned up.
    staging=Path(tempfile.mkdtemp(prefix='.ch2k8-import-',dir=output.parent))
    try:
        with contextlib.redirect_stdout(sys.stderr):
            import_disc(image,staging/'game',direct=True,progress=progress)
        (staging/'game'/'iso-validation.json').write_text(json.dumps(validation, indent=2), encoding='utf-8')
        progress(message='Finalizing loose asset installation...')
        if output.exists():raise ValueError('Installation destination appeared during import; it was left untouched')
        # Windows rename refuses existing destinations, including empty folders.
        (staging/'game').rename(output)
    finally:
        if staging.resolve().parent!=output.parent.resolve() or staging.is_symlink():
            raise ValueError('Unexpected import staging location; cleanup refused')
        shutil.rmtree(staging)
    return dict(game_data=str(output.resolve()),storage='loose-resources')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('output',type=Path,nargs='?')
    parser.add_argument('--inspect',action='store_true',help='Validate ISO identity and archive extents without extracting')
    parser.add_argument('--progress-file',type=Path)
    parser.add_argument('--cancel-file',type=Path)
    args=parser.parse_args()
    try:
        if args.inspect:
            result=inspect_iso(args.image,args.cancel_file)
        else:
            if args.output is None: raise ValueError('Choose an installation destination')
            result=import_iso(args.image,args.output,args.progress_file,args.cancel_file)
    except (Exception,SystemExit) as error:
        print(str(error),file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__=='__main__':sys.exit(main())
