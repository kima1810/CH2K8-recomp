"""Present verified LSU court textures as PNG and synchronize their Xbox base levels."""
import argparse
from functools import cache
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile

BANK = "assets/s258.iff/"
FLOOR = {
    0x49977575: "court_wood",
    0xA37A1E3D: "lsu_center_court_logo",
    0x4F74266F: "cox_sponsor_logo",
    0xAE17F754: "pete_maravich_assembly_center_wordmark",
}
FLOOR_SUPPORT = {
    0xB0F9FBAC: "wood_grayscale_map",
    0xB7CB594F: "purple_paint_swatch",
    0x6D39BEDF: "sec_wordmark_mask",
    0x1F3E00F4: "court_marking_mask_1f3e00f4",
    0x7F94C4CF: "court_marking_mask_7f94c4cf",
    0xBA078A11: "court_marking_mask_ba078a11",
    0xCBA9122E: "court_marking_mask_cba9122e",
    0xDBE6070B: "court_marking_mask_dbe6070b",
}
ARENA = {
    0x20C4269B: "scoreboard_team_fouls",
    0x3C708648: "scoreboard_period",
    0x94DA009F: "scoreboard_home",
    0xC2182546: "scoreboard_guest",
    0xC518AD48: "scoreboard_digits",
    0x450F18D6: "sponsor_banner_atlas",
    0xA290CFA7: "ncaa_banner_atlas",
    0x34BF70A9: "concourse_photo",
}
ARENA_SUPPORT = {
    0x9A8DFFAC: "ambient_occlusion_atlas",
    0xAADCD2BE: "lighting_spot",
    0xB0AF057A: "lighting_glow",
    0xCD85219F: "lighting_point",
    0xFF1C08C9: "light_cookie",
    0xE7BA9D70: "normal_map",
    0x63A021C2: "black_material_sample",
    0x7857B3A2: "dark_material_sample",
    0xE61DC45A: "bordered_material_sample",
}
MARKER = "s258_artwork.json"


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


def present(root):
    marker = root / MARKER
    if marker.exists():
        raise ValueError("The LSU PNG layout is already installed")
    catalog_path = root / "scene_textures.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    dds = studio_dds()
    entries = []
    outputs = {}
    retired = []

    def stage(relative, data):
        path = inside(root, relative)
        if path in outputs or path.exists():
            raise ValueError(f"Artwork destination already exists: {relative}")
        outputs[path] = data

    for scene in catalog["scenes"]:
        for item in scene["textures"]:
            old = item["file"]
            if not old.startswith((BANK + "floor.scne/", BANK + "arena.scne/")):
                continue
            _, bank, folder, *_ = old.split("/")
            parent = f"assets/{bank}/{folder}"
            identity = item["id"]
            floor = folder == "floor.scne"
            role = (FLOOR if floor else ARENA).get(identity)
            support = (FLOOR_SUPPORT if floor else ARENA_SUPPORT).get(identity)
            fmt = item["xbox_format"]
            if not role and not support and fmt in (10, 31, 32, 49, 59, 60):
                support = f"shader_data_{identity:08x}"
            if not role and not support and floor:
                support = f"unclassified_{identity:08x}"
            if not role and not support:
                role = f"surface_{identity:08x}"
            source = inside(root, old)
            current = source.read_bytes()
            if digest(current) != item["sha256"]:
                raise ValueError(f"Preserving an existing DDS edit requires review: {old}")
            if support:
                relative = f"{parent}/_support/{support}.dds"
                if relative != old:
                    stage(relative, current)
                    retired.append(source)
                item.update(file=relative, presentation_file=relative, usage="support")
                continue

            png = f"{parent}/{role}.png"
            backing = f"_runtime/s258-artwork/{folder}/{identity:08x}.dds"
            baseline = backing.removesuffix(".dds") + ".stock.dds"
            stream = io.BytesIO()
            dds.image(current).save(stream, format="PNG")
            image = stream.getvalue()
            for relative, data in ((png, image), (backing, current), (baseline, current)):
                stage(relative, data)
            retired.append(source)
            item.update(file=backing, presentation_file=png, usage="artwork")
            entries.append(dict(png=png, backing=backing, stock=baseline,
                                stock_png_sha256=digest(image)))
    if not any(r["png"].endswith("lsu_center_court_logo.png") for r in entries):
        raise ValueError("The verified LSU center logo is missing from the catalog")
    for path, data in outputs.items():
        write(path, data)
    write_json(catalog_path, catalog)
    write_json(marker, {"version": 1, "textures": entries})
    for path in retired:
        path.unlink()
    return len(entries), sum(item.get("usage") == "support" and
                             item.get("presentation_file", "").startswith(BANK)
                             for row in catalog["scenes"] for item in row["textures"])


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
    marker = root / MARKER
    if not marker.is_file():
        return 0
    state = json.loads(marker.read_text(encoding="utf-8"))
    if state["version"] != 1:
        raise ValueError("Unknown LSU artwork manifest version")
    outputs = {}
    changed = False
    for item in state["textures"]:
        png = inside(root, item["png"])
        target = inside(root, item["backing"])
        baseline = inside(root, item["stock"]).read_bytes()
        current = digest(png.read_bytes())
        if current == item.get("applied_png_sha256"):
            continue
        data = baseline if current == item["stock_png_sha256"] else encode_png(png, baseline, studio_dds())
        if data != target.read_bytes():
            outputs[target] = data
        item["applied_png_sha256"] = current
        changed = True
    for target, data in outputs.items():
        write(target, data)
    if changed:
        write_json(marker, state)
    return len(outputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("present", "sync"))
    parser.add_argument("game", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "present":
            artwork, support = present(args.game.resolve())
            print(f"Created {artwork} editable PNGs and separated {support} support textures.")
        else:
            updated = sync(args.game.resolve())
            if updated:
                print(f"Prepared {updated} edited PNGs for the Xbox loader.")
    except (OSError, ImportError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
