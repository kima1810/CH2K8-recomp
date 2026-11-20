"""Recover loose Xbox asset names by CRC and migrate their path references."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import tempfile
import zlib

SHAPES = ("u", "v", "vtri", "tri", "wishbone")
BUILDS = ("thin", "reg", "fat")
BANK_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\.(?:iff|cdf|bin)")
RECORD_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}")


def crc(name):
    return zlib.crc32(name.encode("ascii"))


def bank_candidates():
    yield from ("eyeball.iff", "lights.iff", "ao_tri.iff", "ao_u.iff",
                "ao_v.iff", "ao_vtri.iff", "ao_wishbone.iff", "baseball.iff",
                "beachball.iff", "coachmode.iff", "createpholder.iff",
                "crowdloops_inside_large.iff", "crowdloops_inside_small.iff",
                "cshoemodel.iff", "darts.iff", "drillschallenge.iff",
                "drillschallenge_attackbasket.iff",
                "drillschallenge_denyposition.iff",
                "drillschallenge_dribblecourse.iff",
                "drillschallenge_linecourse.iff",
                "drillschallenge_shooting.iff", "eightball.iff", "english.iff",
                "golfball.iff", "highlightcreate.iff",
                "loading_drillschallenge.iff", "loading_highlight.iff",
                "ncaaball.iff", "performancepanel.iff", "pontiac_skin.iff",
                "ref1.iff", "ref2.iff", "rockball.iff",
                "sideline_items_crowd01.iff", "sideline_items_crowd01a.iff",
                "sideline_items_crowd01b.iff", "sideline_items_crowd01c.iff",
                "sideline_items_crowd02.iff", "sideline_items_crowd03.iff",
                "skin_english.iff", "studio_sfch2nite.iff",
                "studio_sfsunday.iff", "tennisball.iff", "vcball.iff")
    for side in ("ua", "uh", "ux", "uy", "uz"):
        for selection in ("", "sel"):
            for number in range(1024):
                for suffix in (".iff", ".cdf", ".bin"):
                    yield f"{selection}{side}{number:03d}{suffix}"
    for stem in ("aistreet", "band", "chants", "chatter", "cheerleaders",
                 "cribmusic", "drillmusic", "femusic", "hlmusic", "lines", "loadm",
                 "overlayaudio", "palines", "paplayers", "players", "teams"):
        yield stem + ".bin"
    for stem in ("pcaatface", "pcarmtats", "pcchest", "pcfacehair", "pcfacenormal",
                 "pcfacenormal_dbg", "pchair", "sideline_items"):
        for suffix in (".iff", ".cdf"):
            yield stem + suffix
    for sound in ("ahh", "boo", "cheer-lrg", "cheer-med", "cheer-sml", "freethrow"):
        for direction in ("front", "rear"):
            for venue in ("large", "small"):
                for suffix in (".iff", ".cdf"):
                    yield f"cwd-{sound}-{direction}_{venue}{suffix}"
    yield "cloth_shorts.iff"
    for shape in SHAPES:
        yield f"cloth_{shape}.iff"
        for build in BUILDS:
            yield f"cloth_{shape}_{build}.iff"
    for height in ("hi", "lo"):
        for number in range(1, 5):
            yield f"{height}_shoe{number}.iff"
    for number in (0, 1):
        yield f"shoe_{number}.iff"
    for base in (100, 200, 300, 500):
        for style in range(4):
            for color in range(16):
                yield f"shoe_{base+style}_{color:02d}.iff"


def record_candidates():
    embedded = Path(__file__).with_name("native_assets") / "embedded_record_names.inc"
    yield from re.findall(r'"([A-Za-z][A-Za-z0-9_-]+)"', embedded.read_text(encoding="ascii"))
    yield from ("shoe_upper", "shoe_sole", "unif", "short", "unidata",
                "unifregion", "shortregion", "names", "numbers",
                "jersey_numbers", "midsole_mat", "upper_mat", "toe_mat",
                "heel_mat", "logo_mat", "hitop_mat", "fastener_mat")
    for height in ("hi", "lo"):
        for number in range(1, 5):
            yield f"{height}_shoe{number}"
    for build in BUILDS:
        yield f"shorts{build}"
        for shape in SHAPES:
            yield f"jersey_{shape}_{build}"


def unique_names(candidates, key):
    matches = defaultdict(set)
    for name in candidates:
        matches[key(name)].add(name)
    return {ident: next(iter(names)) for ident, names in matches.items()
            if len(names) == 1}


def contained(root, relative):
    path = root / relative
    final = path.resolve()
    if not final.is_relative_to(root) or path.absolute() != final:
        raise ValueError(f"Linked or out-of-root asset path: {relative}")
    return path


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_temp(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(data)
        temp = Path(stream.name)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def migrate(root, extra, apply):
    asset_file = root / "assets.json"
    manifest = read_json(asset_file)
    if manifest.get("platform") != "xbox360" or manifest.get("storage") != "loose-resources":
        raise ValueError("Select a named Xbox loose-resource installation")
    extra = [line.strip().lower() for line in extra if line.strip()]
    if any(not BANK_PATTERN.fullmatch(name) for name in extra):
        raise ValueError("Additional bank names must be plain Xbox filenames")
    banks = unique_names([*bank_candidates(), *extra], lambda name: crc(name.upper()))
    records = unique_names(record_candidates(), crc)
    loaded = []
    moves = []
    aliases = {}
    unresolved_banks = []
    bank_total = record_total = 0

    for entry in manifest["entries"]:
        old = entry["folder"]
        source = contained(root, old)
        meta = source / "asset.json"
        layout = read_json(meta)
        name = banks.get(entry["hash"]) if source.name.startswith("hash_") else None
        new = f"assets/{name}" if name else old
        if name:
            bank_total += 1
            aliases[old] = new
            entry["legacy_folder"] = old
            moves.append((source, contained(root, new)))
            entry["folder"] = new
        elif source.name.startswith("hash_"):
            unresolved_banks.append(source.name)
        rows = layout.get("records", layout.get("paired_resources", []))
        local = {}
        existing = {row["folder"].casefold() for row in rows}
        for row in rows:
            label = records.get(row["id"], "").lower()
            folder = row["folder"]
            if not label or row.get("name") == label or not re.search(
                    r"_[0-9a-f]{8}(?:_[0-9]{4})?\.", folder):
                continue
            suffix = folder.rsplit(".", 1)[-1]
            target = f"{label}.{suffix}"
            if target.casefold() in existing:
                target = f"{label}_{row['index']:04d}.{suffix}"
            if target.casefold() in existing or not (source / folder).is_dir():
                continue
            record_total += 1
            existing.add(target.casefold())
            local[folder] = target
            aliases[f"{old}/{folder}"] = f"{new}/{target}"
            moves.append((contained(root, f"{new}/{folder}"),
                          contained(root, f"{new}/{target}")))
            row["name"] = label
            row["folder"] = target
        loaded.append((old, new, layout, local))

    def absolute(path):
        if not path.startswith("assets/"):
            return path
        parts = path.split("/")
        for count in range(len(parts), 1, -1):
            key = "/".join(parts[:count])
            if key in aliases:
                return "/".join([aliases[key], *parts[count:]])
        return path

    def rewrite(node, local):
        if isinstance(node, str):
            if node.startswith("assets/"):
                return absolute(node)
            head, slash, tail = node.partition("/")
            return local.get(head, head) + slash + tail
        if isinstance(node, list):
            return [rewrite(item, local) for item in node]
        if isinstance(node, dict):
            result = {k: (v if k in ("legacy_folder", "legacy_path") else rewrite(v, local))
                      for k, v in node.items()}
            folder, path = node.get("folder"), node.get("path")
            if isinstance(folder, str) and folder.startswith("assets/") and isinstance(path, str):
                _, bank, relative = absolute(folder + "/" + path).split("/", 2)
                result.update(folder="assets/" + bank, path=relative)
            return result
        return node

    # Parent directories move first so child paths refer to their final bank.
    moves.sort(key=lambda pair: len(pair[0].parts))
    if len({str(dst).casefold() for _, dst in moves}) != len(moves):
        raise ValueError("Two verified names map to one destination")
    bank_reverse = {new: old for old, new, _, _ in loaded if old != new}
    for src, dst in moves:
        relative = dst.relative_to(root)
        bank = "/".join(relative.parts[:2])
        old_dst = root / bank_reverse.get(bank, bank) / Path(*relative.parts[2:])
        if dst.exists() or (len(relative.parts) > 2 and old_dst.exists()):
            raise ValueError(f"Name already exists: {dst}")

    def encoded(obj):
        return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    writes = {asset_file: encoded(manifest)}
    for old, new, layout, local in loaded:
        relative = rewrite(layout, local)
        if old != new or local or relative != layout:
            writes[root / new / "asset.json"] = encoded(relative)
            rows = relative.get("records", relative.get("paired_resources", []))
            for row in rows:
                old_folder = next((name for name, target in local.items()
                                   if target == row["folder"]), row["folder"])
                original = root / old / old_folder / "record.json"
                if original.is_file():
                    writes[root / new / row["folder"] / "record.json"] = encoded(row)

    for filename in ("scene_textures.json", "asset_edits.json"):
        p = root / filename
        if p.is_file():
            writes[p] = encoded(rewrite(read_json(p), {}))
    for filename in ("assets.map", "native_dds.index", "native_audio.index",
                     "native_dds_choices.index"):
        p = root / filename
        if p.is_file():
            lines = p.read_text(encoding="utf-8").splitlines()
            writes[p] = ("\n".join("\t".join([*parts[:-1], absolute(parts[-1])])
                         for line in lines if (parts := line.split("\t"))) + "\n").encode()
    alias_path = root / "asset_path_aliases.json"
    previous = read_json(alias_path)["paths"] if alias_path.exists() else {}
    aliases_record = {key: absolute(value) for key, value in previous.items()}
    aliases_record.update(aliases)
    writes[alias_path] = encoded(dict(version=1, paths=aliases_record))

    print(json.dumps(dict(banks=bank_total, records=record_total,
                          unresolved_banks=unresolved_banks)))
    if not apply or not moves:
        return

    moved = []
    replaced = []
    try:
        for src, dst in moves:
            src.rename(dst)
            moved.append((src, dst))
        for path, data in writes.items():
            prior = path.read_bytes() if path.exists() else None
            if prior == data:
                continue
            write_temp(path, data)
            replaced.append((path, prior))
    except BaseException:
        for path, prior in reversed(replaced):
            if prior is None:
                path.unlink()
            else:
                write_temp(path, prior)
        for src, dst in reversed(moved):
            dst.rename(src)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path)
    parser.add_argument("--names", type=Path, help="Verified extra Xbox bank names, one per line")
    parser.add_argument("--apply", action="store_true", help="Migrate the installed paths")
    options = parser.parse_args()
    extra = options.names.read_text(encoding="utf-8").splitlines() if options.names else ()
    migrate(options.game.resolve(), extra, options.apply)


if __name__ == "__main__":
    main()
