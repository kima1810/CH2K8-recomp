"""Xbox 360 disc image (XDVDFS / "XGD") lister and extractor.

Layout (all fields LITTLE-endian; public format, see xbox-iso tooling):

  Game partition base: 0 for a trimmed image, 0xFD90000 for an XGD2
  full-disc rip, 0x2080000 / 0x18300000 for XGD1/XGD3 rips (probed).
  Sector size 0x800; sectors are relative to the partition base.

  Volume descriptor @ base + 32 * 0x800
    +000 char[20] "MICROSOFT*XBOX*MEDIA"
    +014 u32 LE   root directory sector
    +018 u32 LE   root directory size (bytes)
    +01C u64 LE   FILETIME
    +7EC char[20] "MICROSOFT*XBOX*MEDIA"

  Directory = binary tree of entries, 4-byte aligned, never spanning a
  sector; 0xFF fill marks the end of a sector's entries.
    +00 u16 LE left subtree offset  (in dwords from directory start, 0 = none)
    +02 u16 LE right subtree offset (in dwords)
    +04 u32 LE start sector
    +08 u32 LE size in bytes
    +0C u8     attributes (0x10 = directory)
    +0D u8     name length
    +0E char[] name
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
from pathlib import Path

from ch2k8_archive import validate_filename

SECTOR = 0x800
MAGIC = b"MICROSOFT*XBOX*MEDIA"
BASES = (0, 0xFD90000, 0x2080000, 0x18300000)
VOLUME = struct.Struct("<20sII")
DIRENT = struct.Struct("<HHIIBB")
ATTR_DIR = 0x10
CHUNK = 8 << 20


def find_base(f) -> int:
    for base in BASES:
        f.seek(base + 32 * SECTOR)
        if f.read(20) == MAGIC:
            return base
    raise SystemExit("no XDVDFS volume descriptor found")


def walk(f, base: int, sector: int, size: int, prefix: str = "", _directories=None, _depth=0):
    """Yield (path, start_sector, size, attributes) depth-first, sorted by name."""
    if size == 0:
        return
    if _directories is None:_directories=set()
    offset=base+sector*SECTOR
    image_size=os.fstat(f.fileno()).st_size
    if _depth>64 or offset in _directories:raise ValueError('Cyclic or excessively deep Xbox ISO directory')
    if not 14<=size<=32<<20 or offset>image_size or size>image_size-offset:
        raise ValueError('Xbox ISO directory exceeds image extent')
    _directories.add(offset)
    f.seek(offset)
    data = f.read(size)
    out = []
    seen = set()
    stack = [0]
    while stack:
        off = stack.pop()
        if off in seen or off + DIRENT.size > len(data):
            raise ValueError('Invalid Xbox ISO directory tree')
        seen.add(off)
        left, right, start, length, attr, nlen = DIRENT.unpack_from(data, off)
        if left == 0xFFFF and right == 0xFFFF:
            continue  # sector fill
        if not nlen or off+DIRENT.size+nlen>len(data):raise ValueError('Truncated Xbox ISO filename')
        name = data[off + DIRENT.size:off + DIRENT.size + nlen].decode("ascii")
        validate_filename(name)
        member_offset=base+start*SECTOR
        if member_offset>image_size or length>image_size-member_offset:raise ValueError('Xbox ISO member exceeds image extent')
        out.append((name, start, length, attr))
        if left:
            stack.append(left * 4)
        if right:
            stack.append(right * 4)
    for name, start, length, attr in sorted(out, key=lambda x: x[0].lower()):
        path = prefix + name
        yield path, start, length, attr
        if attr & ATTR_DIR:
            yield from walk(f, base, start, length, path + "/", _directories, _depth+1)


def open_image(path: Path):
    f = path.open("rb")
    try:
        base = find_base(f)
        f.seek(base + 32 * SECTOR)
        _, root, root_size = VOLUME.unpack(f.read(VOLUME.size))
    except BaseException:
        f.close()
        raise
    return f, base, root, root_size


def cmd_list(args) -> None:
    f, base, root, root_size = open_image(args.image)
    print(f"# partition base {base:#x}, root sector {root:#x}, root size {root_size}")
    for path, start, size, attr in walk(f, base, root, root_size):
        kind = "d" if attr & ATTR_DIR else "-"
        f.seek(base + start * SECTOR)
        magic = f.read(4).hex().upper() if kind == "-" and size else ""
        print(f"{kind} {start:#010x} {size:>12} {magic:8} {path}")


def cmd_extract(args) -> None:
    f, base, root, root_size = open_image(args.image)
    out = Path(args.output).resolve()
    want = {p.lower() for p in args.path or []}
    for path, start, size, attr in walk(f, base, root, root_size):
        if want and path.lower() not in want:
            continue
        dest = out / path
        if dest.resolve() != dest:
            raise ValueError(f"Linked Xbox ISO output path: {path}")
        if attr & ATTR_DIR:
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        f.seek(base + start * SECTOR)
        with dest.open("xb") as o:  # never overwrite
            left = size
            while left:
                chunk = f.read(min(CHUNK, left))
                if not chunk:
                    raise SystemExit(f"short read in {path}")
                o.write(chunk)
                h.update(chunk)
                left -= len(chunk)
        print(f"{size:>12}  sha256={h.hexdigest()[:16]}  {path}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image", type=Path, help="Xbox 360 .iso")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list files with start sector, size and magic")
    p = sub.add_parser("extract", help="extract files (never overwrites)")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--path", nargs="*", help="only these paths (as printed by list)")
    args = ap.parse_args(argv)
    {"list": cmd_list, "extract": cmd_extract}[args.cmd](args)


if __name__ == "__main__":
    main()
