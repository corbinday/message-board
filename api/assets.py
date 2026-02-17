import base64
import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
MANIFEST_PATH = PROJECT_ROOT / "asset-manifest.json"


class StaticAssetResolver:
    """Provides SRI and cache versions for static assets."""

    def __init__(self, static_dir: Path, manifest_path: Path):
        self.static_dir = static_dir
        self.manifest_path = manifest_path
        self._manifest_assets: Dict[str, Dict[str, str]] = {}
        self._manifest_mtime_ns: Optional[int] = None
        self._fallback_cache: Dict[str, Dict[str, str]] = {}
        self._lock = Lock()

    def _load_manifest_if_changed(self) -> None:
        try:
            stat = self.manifest_path.stat()
        except FileNotFoundError:
            self._manifest_assets = {}
            self._manifest_mtime_ns = None
            return

        if self._manifest_mtime_ns == stat.st_mtime_ns:
            return

        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            assets = data.get("assets", {})
            if isinstance(assets, dict):
                self._manifest_assets = assets
            else:
                self._manifest_assets = {}
        except (json.JSONDecodeError, OSError):
            self._manifest_assets = {}

        self._manifest_mtime_ns = stat.st_mtime_ns
        # Clear stale fallback entries when manifest changes.
        self._fallback_cache.clear()

    def _compute_entry(self, asset_path: str) -> Optional[Dict[str, str]]:
        file_path = self.static_dir / asset_path
        try:
            raw = file_path.read_bytes()
        except OSError:
            return None

        sha384 = base64.b64encode(hashlib.sha384(raw).digest()).decode("ascii")
        version = hashlib.sha256(raw).hexdigest()[:16]
        return {"sha384": sha384, "version": version}

    def get_entry(self, asset_path: str) -> Optional[Dict[str, str]]:
        normalized = asset_path.lstrip("/").replace("\\", "/")

        with self._lock:
            self._load_manifest_if_changed()

            manifest_entry = self._manifest_assets.get(normalized)
            if isinstance(manifest_entry, dict):
                if manifest_entry.get("sha384") and manifest_entry.get("version"):
                    return manifest_entry

            if normalized not in self._fallback_cache:
                computed = self._compute_entry(normalized)
                if computed:
                    self._fallback_cache[normalized] = computed

            return self._fallback_cache.get(normalized)

    def get_integrity(self, asset_path: str) -> str:
        entry = self.get_entry(asset_path)
        if not entry:
            return ""
        return f"sha384-{entry['sha384']}"

    def get_version(self, asset_path: str) -> str:
        entry = self.get_entry(asset_path)
        if not entry:
            return ""
        return entry["version"]


asset_resolver = StaticAssetResolver(static_dir=STATIC_DIR, manifest_path=MANIFEST_PATH)
