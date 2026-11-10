"""CH2K8 PS3 USRDIR split archive (0A..0E) reader.

Layout (all fields BIG-endian; see docs/formats/usrdir_archive.md):

  Header @0x00, 6 x u32 BE
    +00 magic        0xAA00B3BF                         [CONFIRMED]
    +04 alignment    offset/size unit (0x800 observed)  [LIKELY]
    +08 part_count                                      [LIKELY]
    +0C zero                                            [GUESS: reserved]
    +10 entry_count                                     [LIKELY]
    +14 zero                                            [GUESS: reserved]
  Part descriptors, part_count x 16 bytes
    +00 u32 BE size in 0x800 units                      [LIKELY]
    +04 u32 BE unknown                                  [GUESS]
    +08 8 bytes UTF-16BE part filename (e.g. "0A")      [LIKELY]
  TOC, entry_count x 16 bytes (4 x u32 BE)
    +00 name hash = CRC32(ASCII uppercase filename)     [LIKELY]
    +04 offset in alignment units (logical space)       [LIKELY]
    +08 unknown                                         [GUESS]
    +0C exact size in BYTES; data is zero/garbage-padded to the next
        alignment boundary (size > gap-0x800 for all 3376 entries)
                                                        [CONFIRMED on JB dump]
  TOC is sorted by hash ascending (binary-search lookup) [LIKELY]

Note: CHoops-Extractor-Reborn treats +0C as alignment units and so flags
every size as impossible; that reading is wrong.

The logical address space is the concatenation of the parts in descriptor
order; entries may straddle part boundaries.

Prior art: ZMO34/CHoops-Extractor-Reborn (choops_py/archive/usrdir_reader.py).
This is an independent reimplementation for verification.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

MAGIC = 0xAA00B3BF
HEADER = struct.Struct(">6I")
PART = struct.Struct(">II8s")
TOC = struct.Struct(">4I")

KNOWN_MAGICS = {
    bytes.fromhex("FF3BEF94"): "IFF standard",
    bytes.fromhex("F0985030"): "IFF CDF-backed metadata",
    bytes.fromhex("0E4837C3"): "H7A compressed",
    bytes.fromhex("326B546C"): "2kTl tool wrapper",
    bytes.fromhex("AA171516"): "IFF name table",
    b"\x89PNG": "PNG",
    b"RIFF": "RIFF",
    b"\x7fELF": "ELF",
    b"SCE\x00": "SCE/SELF",
}


def name_hash(name: str) -> int:
    """CRC32 of the uppercased ASCII filename. [LIKELY]"""
    return zlib.crc32(name.upper().encode("ascii")) & 0xFFFFFFFF


def candidate_names():
    """Filename families documented by CHoops-Extractor-Reborn's namespace."""
    banks = ("frontend frontend_sync global gamedata gamedataextra loading legalpage loc fonts "
             "online playercreate playeditor teamselectlogo arenapics overlaycache jukebox "
             "roster_english streetdata studio studio_preview studio_pontiac dornas crowd "
             "sfx_inside facegen ababall basket chantcreate chantcreate_drums chantcreate_sounds "
             "gameintro gameintro_cameras gameintro_drums gameintro_playerspeech "
             "halftimeadjustments legacy powerbar reelmanual weeklyshow tutorial drilldata shrine "
             "shrine_trophies statefarm kellogg gumbel director").split()
    exts = (".iff", ".cdf", ".bin")
    for b in banks:
        for e in exts:
            yield b + e
    for prefix in ("ua", "uh", "ux", "selua", "seluh", "selux", "s", "m", "p", "coach"):
        for i in range(1000):
            for e in exts:
                yield f"{prefix}{i:03d}{e}"
    for i in range(10000):
        for e in exts:
            yield f"h{i:04d}{e}"


def load_names(extra: list[Path]) -> dict[int, str]:
    names = {name_hash(n): n for n in candidate_names()}
    for p in extra:
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".json":  # {"<decimal hash>": "name"} as in names.json
            for k, v in json.loads(text).items():
                h = int(k)
                if name_hash(v) != h:
                    continue  # only accept pairs we can verify ourselves
                names[h] = v
        else:  # one candidate filename per line
            for line in text.splitlines():
                line = line.strip()
                if line:
                    names[name_hash(line)] = line
    return names


@dataclass
class Part:
    name: str
    units: int
    unknown: int
    raw_name: bytes


@dataclass
class Entry:
    index: int
    hash: int
    offset_units: int
    unknown: int
    size: int
    offset: int = 0
    extent: int = 0          # distance to next entry / end of space
    size_flag: str = ""      # "" | "derived" when stored size is impossible
    name: str | None = None


@dataclass
class Archive:
    root: Path
    magic: int
    alignment: int
    part_count: int
    reserved0: int
    entry_count: int
    reserved1: int
    parts: list[Part] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    header_bytes: bytes = b""

    @property
    def total(self) -> int:
        return sum(p.units * 0x800 for p in self.parts)

    def read(self, offset: int, size: int) -> bytes:
        out = bytearray()
        base = 0
        for p in self.parts:
            psize = p.units * 0x800
            end = base + psize
            if size and base <= offset < end:
                n = min(size, end - offset)
                with (self.root / p.name).open("rb") as f:
                    f.seek(offset - base)
                    chunk = f.read(n)
                if len(chunk) != n:
                    raise ValueError(f"short read in part {p.name}")
                out += chunk
                offset += n
                size -= n
            base = end
        if size:
            raise ValueError("read past end of logical space")
        return bytes(out)

    def serialize_header(self) -> bytes:
        """Rebuild header + part table + TOC from parsed fields."""
        b = bytearray(HEADER.pack(self.magic, self.alignment, self.part_count,
                                  self.reserved0, self.entry_count, self.reserved1))
        for p in self.parts:
            b += PART.pack(p.units, p.unknown, p.raw_name)
        for e in self.entries:
            b += TOC.pack(e.hash, e.offset_units, e.unknown, e.size)
        return bytes(b)


def find_usrdir(path: Path) -> Path:
    for c in (path, path / "USRDIR", path / "PS3_GAME" / "USRDIR"):
        if (c / "0A").is_file():
            return c
    raise SystemExit(f"no 0A found under {path}")


def open_archive(path: Path, names: dict[int, str] | None = None) -> Archive:
    root = find_usrdir(path)
    with (root / "0A").open("rb") as f:
        hdr = f.read(HEADER.size)
        magic, align, na, r0, nf, r1 = HEADER.unpack(hdr)
        if magic != MAGIC:
            raise SystemExit(f"bad magic {magic:08X}")
        if align != 0x800 or not 1 <= na <= 26 or nf > 100_000:
            raise ValueError("Invalid archive alignment or table counts")
        pbytes = f.read(na * PART.size)
        tbytes = f.read(nf * TOC.size)
        if len(pbytes) != na * PART.size or len(tbytes) != nf * TOC.size:
            raise ValueError("Truncated archive tables")
    a = Archive(root, magic, align, na, r0, nf, r1, header_bytes=hdr + pbytes + tbytes)
    for i in range(na):
        units, unk, raw = PART.unpack_from(pbytes, i * PART.size)
        name = raw.decode("utf-16-be").rstrip("\0")
        if len(name) != 2 or name[0] != "0" or not "A" <= name[1] <= "Z":
            raise ValueError("Invalid archive part name")
        a.parts.append(Part(name, units, unk, raw))
    for i in range(nf):
        h, off, unk, size = TOC.unpack_from(tbytes, i * TOC.size)
        a.entries.append(Entry(i, h, off, unk, size, off * align,
                               name=(names or {}).get(h)))
    total = a.total
    ordered = sorted(a.entries, key=lambda e: e.offset)
    for i, e in enumerate(ordered):
        nxt = ordered[i + 1].offset if i + 1 < len(ordered) else total
        e.extent = nxt - e.offset
        if not (e.extent - a.alignment < e.size <= e.extent):
            e.size_flag = "anomaly"
    return a


def sniff(data: bytes) -> str:
    return KNOWN_MAGICS.get(data[:4], "unknown")


# ---------------------------------------------------------------- rebuild
#
# The retail layout is tight: every entry starts on an alignment boundary
# directly after the previous one (gap == align_up(size)), padding is zero,
# and data starts at the first boundary after the TOC. [CONFIRMED on JB dump]
# Rebuilding keeps the original offset order and TOC (hash) order, so an
# unmodified rebuild is byte-identical; replaced entries may grow or shrink
# and everything after them moves.

CHUNK = 8 << 20
DEFAULT_PART_UNITS = 0x80000  # 1 GiB, as in 0A..0D


def align_up(n: int, a: int) -> int:
    return -(-n // a) * a


def part_raw_name(i: int) -> bytes:
    # Names past the retail "0E" follow the same pattern. [GUESS] whether the
    # game opens parts by descriptor name or by a hardcoded list is unknown.
    return f"0{chr(ord('A') + i)}".encode("utf-16-be").ljust(8, b"\0")


@dataclass
class Placement:
    entry: Entry           # original entry (offset/size in the source archive)
    offset: int            # new logical byte offset
    size: int              # new byte size
    source: Path | None    # replacement file, or None to copy the original bytes


def plan_rebuild(a: Archive, replace: dict[int, Path]) -> tuple[Archive, list[Placement]]:
    """Lay out a new archive; returns its header model and the data placements."""
    unknown = set(replace) - {e.hash for e in a.entries}
    if unknown:
        raise SystemExit("replacement not in TOC: " + ", ".join(f"{h:08X}" for h in sorted(unknown)))
    sizes = {e.hash: e.size for e in a.entries}
    for h, p in replace.items():
        sizes[h] = p.stat().st_size
    max_units = a.parts[0].units if a.part_count > 1 else DEFAULT_PART_UNITS
    part_count = a.part_count
    while True:  # header length depends on part_count, which depends on layout
        pos = align_up(HEADER.size + part_count * PART.size + len(a.entries) * TOC.size, a.alignment)
        placements = []
        for e in sorted(a.entries, key=lambda e: e.offset):
            placements.append(Placement(e, pos, sizes[e.hash], replace.get(e.hash)))
            pos += align_up(sizes[e.hash], a.alignment)
        total_units = pos // a.alignment
        units = [max_units] * (total_units // max_units)
        if total_units % max_units:
            units.append(total_units % max_units)
        if len(units) == part_count:
            break
        part_count = len(units)

    parts = []
    for i, u in enumerate(units):
        old = a.parts[i] if i < len(a.parts) else None
        raw = old.raw_name if old else part_raw_name(i)
        parts.append(Part(raw.decode("utf-16-be").rstrip("\0"), u, old.unknown if old else 0, raw))
    new_off = {pl.entry.hash: pl for pl in placements}
    entries = []
    for e in a.entries:  # TOC order (hash-sorted) is preserved
        pl = new_off[e.hash]
        entries.append(Entry(e.index, e.hash, pl.offset // a.alignment, e.unknown, pl.size,
                             pl.offset, align_up(pl.size, a.alignment), name=e.name))
    new = Archive(a.root, a.magic, a.alignment, len(parts), a.reserved0, len(entries),
                  a.reserved1, parts, entries)
    return new, placements


def iter_rebuilt(a: Archive, new: Archive, placements: list[Placement]):
    """Yield the rebuilt logical space as byte chunks."""
    head = new.serialize_header()
    yield head
    pos = len(head)
    for pl in placements:
        if pl.offset > pos:
            yield bytes(pl.offset - pos)
        pos = pl.offset
        if pl.source is None:
            done = 0
            while done < pl.size:
                n = min(CHUNK, pl.size - done)
                yield a.read(pl.entry.offset + done, n)
                done += n
        else:
            done = 0
            with pl.source.open("rb") as f:
                while chunk := f.read(CHUNK):
                    done += len(chunk)
                    yield chunk
            if done != pl.size:
                raise SystemExit(f"{pl.source} changed size while reading")
        pos += pl.size
    if new.total > pos:
        yield bytes(new.total - pos)


def write_parts(root: Path, parts: list[Part], chunks) -> None:
    """Split a logical byte stream across part files."""
    it = iter(chunks)
    buf = b""
    for p in parts:
        need = p.units * 0x800
        with (root / p.name).open("xb") as f:  # never overwrite
            while need:
                if not buf:
                    buf = next(it)
                n = min(need, len(buf))
                f.write(buf[:n])
                buf = buf[n:]
                need -= n
    if buf or next(it, b""):
        raise SystemExit("rebuilt stream longer than part table")


def compare_stream(a: Archive, chunks) -> int | None:
    """Return the first differing logical offset vs the source archive, or None."""
    pos = 0
    for chunk in chunks:
        if pos + len(chunk) > a.total:
            return a.total
        orig = a.read(pos, len(chunk))
        if orig != chunk:
            return pos + next(i for i, (x, y) in enumerate(zip(orig, chunk)) if x != y)
        pos += len(chunk)
    return None if pos == a.total else pos


def parse_replacements(files: list[Path], dirs: list[Path]) -> dict[int, Path]:
    """Map name hash -> file. Accepts real filenames, or the extract fallback
    name for unresolved entries ("00012_ABCD1234.bin")."""
    paths = list(files)
    for d in dirs:
        paths += sorted(p for p in d.iterdir() if p.is_file())
    out: dict[int, Path] = {}
    for p in paths:
        stem = p.stem
        if len(stem) == 14 and stem[5] == "_" and stem[:5].isdigit():
            h = int(stem[6:], 16)
        else:
            h = name_hash(p.name)
        if h in out:
            raise SystemExit(f"two replacements for {h:08X}: {out[h]} and {p}")
        out[h] = p
    return out


# ---------------------------------------------------------------- commands

def cmd_info(a: Archive, args) -> None:
    print(f"root          {a.root}")
    print(f"magic         {a.magic:08X}")
    print(f"alignment     {a.alignment:#x}")
    print(f"parts         {a.part_count}  reserved0={a.reserved0:#x} reserved1={a.reserved1:#x}")
    for p in a.parts:
        pf = a.root / p.name
        on_disk = pf.stat().st_size if pf.is_file() else None
        flag = ("  MISSING" if on_disk is None else
                "" if on_disk == p.units * 0x800 else f"  MISMATCH on-disk={on_disk}")
        print(f"  {p.name:4} units={p.units:#x} bytes={p.units * 0x800} unknown={p.unknown:#x}{flag}")
    print(f"entries       {a.entry_count}")
    print(f"header+toc    {len(a.header_bytes):#x} bytes")
    print(f"named         {sum(1 for e in a.entries if e.name)} / {a.entry_count}")
    print(f"size anomalies {sum(1 for e in a.entries if e.size_flag)}  (size not within last unit of extent)")
    print(f"toc unknown@8 {Counter(e.unknown for e in a.entries).most_common(8)}")
    first = min(e.offset for e in a.entries)
    print(f"first data    {first:#x}")


def cmd_verify(a: Archive, args) -> None:
    rebuilt = a.serialize_header()
    ok = rebuilt == a.header_bytes
    print(f"header/part/TOC round-trip: {'IDENTICAL' if ok else 'DIFFERS'} ({len(rebuilt)} bytes)")
    hashes = Counter(e.hash for e in a.entries)
    dups = {h: c for h, c in hashes.items() if c > 1}
    print(f"duplicate hashes: {len(dups)}")
    offs = sorted(e.offset for e in a.entries)
    print(f"monotonic TOC offsets: {[e.offset for e in a.entries] == offs}")
    print(f"min entry gap: {min(b - x for x, b in zip(offs, offs[1:]))}")
    hs = [e.hash for e in a.entries]
    print(f"TOC sorted by hash: {hs == sorted(hs)}")
    sys.exit(0 if ok else 1)


def cmd_list(a: Archive, args) -> None:
    out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    w = csv.writer(out)
    w.writerow(["index", "hash", "name", "offset", "size", "extent", "size_flag",
                "toc_unknown", "magic", "kind"])
    for e in a.entries:
        head = a.read(e.offset, min(16, e.extent))
        w.writerow([e.index, f"{e.hash:08X}", e.name or "", f"{e.offset:#x}", e.size,
                    e.extent, e.size_flag, f"{e.unknown:#x}", head[:4].hex().upper(), sniff(head)])
    if out is not sys.stdout:
        out.close()


def validate_filename(name: str) -> None:
    """Accept one portable filename without Windows path or device aliases."""
    stem = name.split(".", 1)[0].rstrip(" ").upper()
    devices = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    numbered_device = (len(stem) == 4 and stem[:3] in {"COM", "LPT"}
                       and stem[3] in "0123456789¹²³")
    if (not name or name.endswith((".", " ")) or stem in devices or numbered_device
            or any(ord(c) < 32 or c in '/\\:<>"|?*' for c in name)):
        raise ValueError(f"Unsafe extraction filename: {name!r}")


def cmd_extract(a: Archive, args) -> None:
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    sel = a.entries
    if args.index is not None:
        sel = [e for e in sel if e.index in args.index]
    if args.name:
        want = {name_hash(n) for n in args.name}
        sel = [e for e in sel if e.hash in want]
    for e in sel:
        size = e.extent if args.full_extent else e.size
        name = e.name or f"{e.index:05d}_{e.hash:08X}.bin"
        validate_filename(name)
        fn = out / name
        data = a.read(e.offset, size)
        try:
            with fn.open("xb") as output:
                output.write(data)
        except FileExistsError:
            raise SystemExit(f"refusing to overwrite {fn}") from None
        print(f"{e.index:5} {fn.name:32} {size:>10}  sha256={hashlib.sha256(data).hexdigest()[:16]}")


def cmd_rebuild(a: Archive, args) -> None:
    replace = parse_replacements(args.replace, args.replace_dir)
    new, placements = plan_rebuild(a, replace)
    moved = sum(1 for pl in placements if pl.offset != pl.entry.offset)
    print(f"replacements  {len(replace)}")
    for pl in placements:
        if pl.source:
            print(f"  {pl.entry.name or f'{pl.entry.hash:08X}':32} {pl.entry.size:>10} -> {pl.size:>10}")
    print(f"moved entries {moved} / {len(placements)}")
    print(f"parts         {a.part_count} -> {new.part_count}  "
          f"({', '.join(f'{p.name}={p.units:#x}' for p in new.parts)})")
    if new.part_count != a.part_count:
        print("WARNING: part count changed; whether the game honors the descriptor table is unverified")
    if args.check:
        diff = compare_stream(a, iter_rebuilt(a, new, placements))
        print("rebuild vs source: " + ("IDENTICAL" if diff is None else f"DIFFERS at {diff:#x}"))
        sys.exit(0 if diff is None else 1)
    out = Path(args.output)
    if out.resolve() == a.root.resolve():
        raise SystemExit("output must not be the source USRDIR")
    out.mkdir(parents=True, exist_ok=True)
    clash = [p.name for p in new.parts if (out / p.name).exists()]
    if clash:
        raise SystemExit(f"refusing to overwrite {', '.join(clash)} in {out}")
    write_parts(out, new.parts, iter_rebuilt(a, new, placements))
    b = open_archive(out)
    ok = b.serialize_header() == new.serialize_header() and not any(e.size_flag for e in b.entries)
    for pl in placements:
        if pl.source:
            e = next(x for x in b.entries if x.hash == pl.entry.hash)
            ok &= b.read(e.offset, e.size) == pl.source.read_bytes()
    print(f"wrote {out}  readback {'OK' if ok else 'FAILED'}")
    sys.exit(0 if ok else 1)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("usrdir", type=Path, help="USRDIR (or a parent) containing 0A..0E")
    ap.add_argument("--names", type=Path, action="append", default=[],
                    help="extra names: .json {hash:name} or text (one filename per line). "
                         "Only pairs whose CRC32 we reproduce are used.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="print header, parts and TOC summary")
    sub.add_parser("verify", help="round-trip header/part/TOC bytes")
    p = sub.add_parser("list", help="CSV listing of all entries with magic sniffing")
    p.add_argument("-o", "--output")
    p = sub.add_parser("extract", help="extract entries (never overwrites)")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--index", type=int, nargs="*")
    p.add_argument("--name", nargs="*")
    p.add_argument("--full-extent", action="store_true",
                   help="extract up to the next entry (includes padding)")
    p = sub.add_parser("rebuild", help="write a new 0A.. archive, optionally replacing entries "
                                       "(entries may grow/shrink; later entries are relocated)")
    p.add_argument("-o", "--output", help="output directory for the new parts")
    p.add_argument("--replace", type=Path, nargs="*", default=[],
                   help="replacement files, matched by filename hash (or NNNNN_HASH.bin)")
    p.add_argument("--replace-dir", type=Path, action="append", default=[],
                   help="directory of replacement files (non-recursive)")
    p.add_argument("--check", action="store_true",
                   help="don't write; compare the rebuilt stream with the source archive")
    args = ap.parse_args(argv)
    if args.cmd == "rebuild" and not (args.check or args.output):
        ap.error("rebuild needs -o or --check")
    a = open_archive(args.usrdir, load_names(args.names))
    {"info": cmd_info, "verify": cmd_verify, "list": cmd_list, "extract": cmd_extract,
     "rebuild": cmd_rebuild}[args.cmd](a, args)


if __name__ == "__main__":
    main()
