#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_JS_DIR = PROJECT_ROOT / "static" / "js"
MANIFEST_PATH = PROJECT_ROOT / "asset-manifest.json"


def _iter_js_files() -> List[Path]:
    if not STATIC_JS_DIR.exists():
        return []
    return sorted(
        [path for path in STATIC_JS_DIR.rglob("*.js") if path.is_file()],
        key=lambda p: p.as_posix(),
    )


def _relative_asset_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT / "static").as_posix()


def _hash_entry(path: Path) -> Dict[str, str]:
    raw = path.read_bytes()
    sha384 = base64.b64encode(hashlib.sha384(raw).digest()).decode("ascii")
    version = hashlib.sha256(raw).hexdigest()[:16]
    return {"sha384": sha384, "version": version}


def _snapshot(files: List[Path]) -> Tuple[Tuple[str, int, int], ...]:
    rows = []
    for path in files:
        stat = path.stat()
        rows.append((_relative_asset_path(path), stat.st_mtime_ns, stat.st_size))
    return tuple(rows)


def build_manifest() -> Dict[str, object]:
    files = _iter_js_files()
    assets: Dict[str, Dict[str, str]] = {}
    for path in files:
        assets[_relative_asset_path(path)] = _hash_entry(path)

    return {
        "algorithm": "sha384",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assets": assets,
    }


def write_manifest() -> None:
    manifest = build_manifest()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = MANIFEST_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(MANIFEST_PATH)
    print(
        f"Wrote {MANIFEST_PATH} with {len(manifest.get('assets', {}))} JS assets.",
        flush=True,
    )


def watch(interval_seconds: float) -> None:
    print(f"Watching {STATIC_JS_DIR} for JS changes...", flush=True)
    write_manifest()
    last_snapshot = _snapshot(_iter_js_files())
    while True:
        files = _iter_js_files()
        current = _snapshot(files)
        if current != last_snapshot:
            write_manifest()
            last_snapshot = current
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SRI + version manifest for static JS assets."
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch static/js and regenerate the manifest when files change.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Generate manifest once and exit (default behavior).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Watch polling interval in seconds (default: 1.0).",
    )
    args = parser.parse_args()

    if args.watch:
        watch(interval_seconds=max(0.25, args.interval))
        return

    # Default: generate once.
    write_manifest()


if __name__ == "__main__":
    main()
