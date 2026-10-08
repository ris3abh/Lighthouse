"""Zip the capture extension for "Load unpacked" (unzip, then load the folder) or a store upload.

python scripts/package_extension.py   ->  dist/areao1-capture-<version>.zip
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "areao1" / "extension"


def main() -> Path:
    version = json.loads((EXT / "manifest.json").read_text())["version"]
    out = ROOT / "dist" / f"areao1-capture-{version}.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(EXT.iterdir()):
            if f.is_file():
                z.write(f, f"areao1-capture/{f.name}")
    print(out)
    return out


if __name__ == "__main__":
    main()
