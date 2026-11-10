import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ch2k8_archive as ar  # noqa: E402

REAL = Path(__file__).resolve().parents[1] / "work/ch2k8/College Hoops 2K8 (USA)/PS3_GAME/USRDIR"


def build_synthetic(root: Path, files: dict[str, bytes], part_units: int = 4):
    """Write a two-part archive; entries hash-sorted, data offset-shuffled."""
    align = 0x800
    names = list(files)
    toc_end = 24 + 2 * 16 + len(names) * 16
    pos = -(-toc_end // align)  # first data unit
    placed = {}
    for n in reversed(names):  # reversed so offsets aren't hash-ordered
        placed[n] = pos
        pos += -(-len(files[n]) // align)
    total_units = max(pos, part_units + 1)
    space = bytearray(total_units * align)
    for n, u in placed.items():
        space[u * align:u * align + len(files[n])] = files[n]
    hdr = struct.pack(">6I", ar.MAGIC, align, 2, 0, len(names), 0)
    sizes = [part_units, total_units - part_units]
    for i, s in enumerate(sizes):
        hdr += struct.pack(">II8s", s, 0, f"0{chr(65 + i)}".encode("utf-16-be").ljust(8, b"\0"))
    for n in sorted(names, key=ar.name_hash):
        hdr += struct.pack(">4I", ar.name_hash(n), placed[n], 0, len(files[n]))
    space[:len(hdr)] = hdr
    (root / "0A").write_bytes(space[:sizes[0] * align])
    (root / "0B").write_bytes(space[sizes[0] * align:])


def test_synthetic_roundtrip_and_read(tmp_path):
    files = {"ua000.iff": b"\xff\x3b\xef\x94" + b"A" * 3000,
             "roster_english.iff": b"\xff\x3b\xef\x94" + b"B" * 5000,  # straddles 0A/0B
             "x.bin": b"C" * 10}
    build_synthetic(tmp_path, files)
    a = ar.open_archive(tmp_path, {ar.name_hash(n): n for n in files})
    assert a.serialize_header() == a.header_bytes
    assert all(not e.size_flag for e in a.entries)
    for e in a.entries:
        assert a.read(e.offset, e.size) == files[e.name]


def test_name_hash_is_case_insensitive():
    assert ar.name_hash("UA000.IFF") == ar.name_hash("ua000.iff")


@pytest.mark.skipif(not (REAL / "0A").is_file(), reason="real USRDIR not extracted to work/")
def test_real_header_roundtrip():
    a = ar.open_archive(REAL)
    assert a.magic == ar.MAGIC and a.alignment == 0x800
    assert a.serialize_header() == a.header_bytes
    assert [e.hash for e in a.entries] == sorted(e.hash for e in a.entries)
    assert not any(e.size_flag for e in a.entries)


@pytest.mark.parametrize("name", ["../escape.bin", r"..\escape.bin", "x:stream", "NUL.txt", "COM1 .bin", "file. "])
def test_extraction_rejects_unsafe_name_map(tmp_path, name):
    from types import SimpleNamespace

    build_synthetic(tmp_path, {name: b"test"})
    names = tmp_path / "names.json"
    names.write_text(json.dumps({ar.name_hash(name): name}), encoding="utf-8")
    archive = ar.open_archive(tmp_path, ar.load_names([names]))
    args = SimpleNamespace(output=tmp_path / "output", index=None, name=None, full_extent=False)
    with pytest.raises(ValueError, match="Unsafe extraction filename"):
        ar.cmd_extract(archive, args)
    assert list(args.output.iterdir()) == []


def test_archive_rejects_path_in_part_table(tmp_path):
    build_synthetic(tmp_path, {"file.bin": b"test"})
    part = tmp_path / "0A"
    data = bytearray(part.read_bytes())
    data[32:40] = "../x".encode("utf-16-be")
    part.write_bytes(data)
    with pytest.raises(ValueError, match="Invalid archive part name"):
        ar.open_archive(tmp_path)
