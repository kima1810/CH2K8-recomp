"""Run ReXGlue without making an unchanged manifest newer than its outputs."""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from pathlib import Path

from fix_codegen import correct_directory
from optimize_codegen import optimize_directory
from gpu_wait_codegen import prepare_directory as prepare_gpu_wait


def run_codegen(executable: Path, manifest: Path, generated: Path | None = None) -> int:
    original = manifest.read_bytes()
    metadata = manifest.stat()
    previous = {}
    if generated:
        for path in generated.glob("*.cpp"):
            previous[path] = (hashlib.sha256(path.read_bytes()).digest(), path.stat())
    result = subprocess.run([str(executable), "codegen", str(manifest)], check=False)
    if result.returncode == 0:
        if generated:
            total, changed = correct_directory(generated)
            print(f"vupkd3d128: corrected {total} expressions in {changed} files", flush=True)
            optimized = optimize_directory(generated)
            print(f"hot functions: prepared {optimized} paired pack sites", flush=True)
            gpu_waits=prepare_gpu_wait(generated)
            print(f"GPU progress waits: prepared {gpu_waits} files",flush=True)
            # The SDK can rewrite a corrected file back to the broken form.
            # If correction restores identical bytes, avoid a pointless rebuild.
            for path, (digest, stat) in previous.items():
                if path.exists() and hashlib.sha256(path.read_bytes()).digest() == digest:
                    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        if manifest.read_bytes() == original:
            os.utime(manifest, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("generated", type=Path, nargs="?")
    args = parser.parse_args()
    return run_codegen(args.executable.resolve(), args.manifest.resolve(),
                       args.generated.resolve() if args.generated else None)


if __name__ == "__main__":
    raise SystemExit(main())
