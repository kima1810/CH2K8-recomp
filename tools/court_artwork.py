"""Present named court artwork as PNG and synchronize its Xbox base levels."""
import argparse
from functools import cache
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile

MARKER = "court_artwork.json"
LEGACY_MARKER = "s258_artwork.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Artwork path escapes the game folder: {relative}")
    return path


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(data)
        scratch = Path(temp.name)
    try:
        scratch.replace(path)
    finally:
        scratch.unlink(missing_ok=True)


def write_json(path, content):
    write(path, (json.dumps(content, indent=2) + "\n").encode())


@cache
def studio_dds():
    studio = Path(__file__).resolve().parents[2] / "CHoops-Extractor-Reborn-Recomp"
    sys.path[:0] = [str(studio / "output/python-deps"), str(studio)]
    from choops_recomp import dds
    return dds


def read_manifest(root):
    for name in (MARKER, LEGACY_MARKER):
        path = root / name
        if path.is_file():
            state = json.loads(path.read_text(encoding="utf-8"))
            if state["version"] != 1:
                raise ValueError("Unknown court artwork manifest version")
            return path, state["textures"]
    return None, []


def material_stem(item, repeated):
    geometry = item.get("geometry", [])
    roles = item.get("roles", [])
    prefix = f"{geometry[0]}_" if len(geometry) == 1 else ""
    material = roles[0] if len(roles) == 1 else "texture"
    stem = f"{prefix}{material}_{item['id']:08x}"
    return f"{stem}_{item['slot']:04d}" if repeated else stem


def present(root):
    from collections import Counter

    catalog_path = root / "scene_textures.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    manifest_path, prior = read_manifest(root)
    entries = {entry["png"]: entry for entry in prior}
    dds = studio_dds()
    converted, renamed = 0, 0
    courts = set()

    with tempfile.TemporaryDirectory(dir=root, prefix=".court-artwork-") as temp:
        staging = Path(temp)
        outputs = {}
        retired = {}

        def stage(relative, data):
            path = inside(root, relative)
            if path in outputs or path.exists():
                raise ValueError(f"Court artwork destination already exists: {relative}")
            pending = staging / str(len(outputs))
            pending.write_bytes(data)
            outputs[path] = pending

        for scene in catalog["scenes"]:
            repeats = Counter(item["id"] for item in scene["textures"])
            for item in scene["textures"]:
                display = item.get("presentation_file", item["file"])
                parts = display.split("/")
                if len(parts) < 4 or parts[0] != "assets":
                    continue
                _, bank, folder, *_ = parts
                is_floor = folder == "floor.scne" or (
                    folder.startswith("floor_") and folder.endswith(".scne"))
                is_lsu_arena = bank == "s258.iff" and folder == "arena.scne"
                if not is_floor and not is_lsu_arena:
                    continue
                if is_floor:
                    courts.add((bank, folder))

                parent = f"assets/{bank}/{folder}"
                stem = material_stem(item, repeats[item["id"]] > 1)
                usage = item.get("usage")
                source = inside(root, item["file"])
                current = source.read_bytes() if usage == "artwork" and display.lower().endswith(".dds") else None
                # DDS cubemaps are shader inputs with six faces, even when a
                # material uses one through a sampler labeled diffuse.
                cubemap = current is not None and bool(int.from_bytes(current[112:116], "little") & 0x200)
                if usage == "support" or cubemap:
                    if cubemap or bank == "s258.iff" or "/_support/" not in item["file"]:
                        replacement = f"{parent}/_support/{stem}.dds"
                        if replacement != item["file"]:
                            data = current if current is not None else source.read_bytes()
                            stage(replacement, data)
                            retired[source] = digest(data)
                            item.update(file=replacement, presentation_file=replacement, usage="support")
                            renamed += 1
                    continue
                if usage != "artwork":
                    continue

                png = f"{parent}/{stem}.png"
                if display.lower().endswith(".png"):
                    if display != png:
                        entry = entries.pop(display)
                        old = inside(root, display)
                        data = old.read_bytes()
                        stage(png, data)
                        retired[old] = digest(data)
                        entry["png"] = png
                        entries[png] = entry
                        item["presentation_file"] = png
                        renamed += 1
                    continue

                # The current DDS may contain a user edit. Carry its bytes and
                # keep the catalog's original Xbox digest for runtime comparison.
                backing = f"_runtime/court-artwork/{bank}/{folder}/{item['slot']:04d}.dds"
                baseline = backing.removesuffix(".dds") + ".stock.dds"
                stream = io.BytesIO()
                try:
                    dds.image(current).save(stream, format="PNG")
                except (OSError, ValueError, NotImplementedError) as exc:
                    raise ValueError(f"Could not decode court texture {display}: {exc}") from exc
                image = stream.getvalue()
                for relative, data in ((png, image), (backing, current), (baseline, current)):
                    stage(relative, data)
                retired[source] = digest(current)
                item.update(file=backing, presentation_file=png)
                entries[png] = dict(png=png, backing=backing, stock=baseline,
                                    stock_png_sha256=digest(image),
                                    applied_png_sha256=digest(image))
                converted += 1

        available = {(parts[1], parts[2]) for name in entries if
                     len(parts := name.split("/")) >= 4}
        if missing := courts - available:
            raise ValueError(f"No editable court artwork found for {sorted(missing)}")
        if not outputs and manifest_path == root / MARKER:
            return len(courts), 0, 0
        for path, expected in retired.items():
            if digest(path.read_bytes()) != expected:
                raise ValueError(f"Source artwork changed during preparation: {path}")
        for path, pending in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            pending.rename(path)
        write_json(catalog_path, catalog)
        write_json(root / MARKER, {"version": 1, "textures": list(entries.values())})
        if manifest_path == root / LEGACY_MARKER:
            manifest_path.unlink()
        for path in retired:
            path.unlink()
    return len(courts), converted, renamed


def encode_png(path, baseline, dds):
    from PIL import Image
    with Image.open(path) as source:
        before = dds.image(baseline)
        if source.size != before.size:
            raise ValueError(f"Artwork must retain {before.width}x{before.height}: {path.name}")
        after = source.convert("RGBA")
    if before.tobytes() == after.tobytes():
        return baseline
    info = dds.info(baseline)
    if "raw_format" in info:
        return dds.from_image(path, baseline, mipmaps=False)

    code = info["fourcc"].encode()
    encoded = dds._encode_level(after, code)
    block_bytes = 8 if code in (b"DXT1", b"ATI1") else 16
    if len(encoded) != len(baseline) - 128 or info["mips"] != 1:
        raise ValueError(f"Unexpected Xbox base level: {path.name}")
    result = bytearray(baseline)
    before_bytes, after_bytes = before.tobytes(), after.tobytes()
    width, height = before.size
    blocks_wide = math.ceil(width / 4)
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            rows = ((row * width + x) * 4 for row in range(y, min(y + 4, height)))
            count = min(width - x, 4) * 4
            if any(before_bytes[i:i+count] != after_bytes[i:i+count] for i in rows):
                offset = (y // 4 * blocks_wide + x // 4) * block_bytes
                result[128 + offset:128 + offset + block_bytes] = encoded[offset:offset + block_bytes]
    return bytes(result)


def sync(root):
    marker, textures = read_manifest(root)
    if marker is None:
        return 0
    outputs = {}
    changed = False
    for item in textures:
        png = inside(root, item["png"])
        target = inside(root, item["backing"])
        current = digest(png.read_bytes())
        if current == item.get("applied_png_sha256"):
            continue
        baseline = inside(root, item["stock"]).read_bytes()
        data = baseline if current == item["stock_png_sha256"] else encode_png(png, baseline, studio_dds())
        if data != target.read_bytes():
            outputs[target] = data
        item["applied_png_sha256"] = current
        changed = True
    for target, data in outputs.items():
        write(target, data)
    if changed:
        write_json(marker, {"version": 1, "textures": textures})
    return len(outputs)


def restore_dds(root, archive):
    """Sync legacy PNG edits and return their catalog entries to loose DDS."""
    if archive.is_relative_to(root) or root.is_relative_to(archive):
        raise ValueError("PNG archive must be outside the game folder")
    marker, entries = read_manifest(root)
    if marker is None:
        return 0, 0
    if archive.exists():
        raise ValueError(f"PNG archive already exists: {archive}")
    catalog_path = root / "scene_textures.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_presentation = {t.get("presentation_file"): t
                       for scene in catalog["scenes"] for t in scene["textures"]
                       if t.get("presentation_file")}
    plan = []
    for entry in entries:
        relative = entry["png"]
        item = by_presentation[relative]
        if item["file"] != entry["backing"]:
            raise ValueError(f"Catalog backing differs for {relative}")
        png = inside(root, relative)
        dds = png.with_suffix(".dds")
        if dds.exists():
            raise ValueError(f"DDS destination already exists: {dds}")
        plan.append((item, png, dds, inside(root, entry["backing"]),
                     inside(archive, relative)))

    synchronized = sync(root)
    for item, png, dds, backing, backup in plan:
        write(backup, png.read_bytes())
        data = backing.read_bytes()
        if data[:4] != b"DDS ":
            raise ValueError(f"Invalid DDS backing: {backing}")
        write(dds, data)
        relative = dds.relative_to(root).as_posix()
        item.update(file=relative, presentation_file=relative)
    write(archive / marker.name, marker.read_bytes())
    write_json(catalog_path, catalog)
    marker.unlink()
    for _, png, _, _, _ in plan:
        png.unlink()
    return len(plan), synchronized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("present", "sync", "restore-dds"))
    parser.add_argument("game", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "present":
            courts, artwork, renamed = present(args.game.resolve())
            print(f"{courts} courts covered, {artwork} editable PNGs created, {renamed} files renamed.")
        elif args.action == "restore-dds":
            if args.archive is None:
                parser.error("restore-dds requires --archive outside the game folder")
            restored, edited = restore_dds(args.game.resolve(), args.archive.resolve())
            print(f"Restored {restored} DDS files and synchronized {edited} PNG edits.")
        else:
            updated = sync(args.game.resolve())
            if updated:
                print(f"Prepared {updated} edited PNGs for the Xbox loader.")
    except (OSError, ImportError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
