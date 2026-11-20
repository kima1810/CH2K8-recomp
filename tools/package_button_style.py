"""Compatibility entry point for the Studio-hosted SDK artwork packager."""
import runpy
from pathlib import Path
if __name__=="__main__":runpy.run_path(str(Path(__file__).resolve().parents[1]/"sdk/package_button_style.py"),run_name="__main__")
