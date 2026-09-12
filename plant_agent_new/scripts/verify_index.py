"""Verify the three prebuilt index files using the committed manifest."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "data/index-manifest.json").read_text(encoding="utf-8"))
failed = False
for relative, expected in sorted(manifest.items()):
    path = ROOT / relative
    if not path.is_file():
        print(f"MISSING {relative}")
        failed = True
        continue
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    valid = path.stat().st_size == expected["bytes"] and digest.hexdigest() == expected["sha256"]
    print(f"{'OK' if valid else 'MISMATCH'} {relative}")
    failed |= not valid
raise SystemExit(1 if failed else 0)
