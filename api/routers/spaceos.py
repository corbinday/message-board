"""
api/routers/spaceos.py — SpaceOS OTA update endpoint.

The pre-signed bundle (spaceos-update.bin) is committed to the repo and never
generated or signed here. This module:
  - Reads spaceos-update.bin from the project root at startup.
  - Computes its SHA-256 hash once and caches it.
  - Serves GET /api/spaceos/check for board-authenticated OTA checks.
"""
import hashlib
import logging
import os
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import Response
from werkzeug.security import check_password_hash

import api.queries as q

router = APIRouter()
logger = logging.getLogger(__name__)

# spaceos-update.bin lives at the project root (two levels above api/routers/)
_BUNDLE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "spaceos-update.bin")
)

# Cached (bundle_bytes, sha256_hex) — loaded once on first request (or at startup).
_bundle_cache: tuple[bytes, str] | None = None
_bundle_loaded: bool = False


def load_bundle() -> tuple[bytes, str] | None:
    """
    Load spaceos-update.bin and cache (bytes, sha256_hex).
    Returns None if no bundle exists.
    """
    global _bundle_cache, _bundle_loaded
    if _bundle_loaded:
        return _bundle_cache

    _bundle_loaded = True
    if not os.path.exists(_BUNDLE_PATH):
        logger.info("spaceos-update.bin not found — OTA updates not available")
        return None

    bundle_bytes = open(_BUNDLE_PATH, "rb").read()
    bundle_hash = hashlib.sha256(bundle_bytes).hexdigest()
    _bundle_cache = (bundle_bytes, bundle_hash)
    logger.info(
        f"SpaceOS bundle loaded: {len(bundle_bytes)} bytes, "
        f"hash={bundle_hash[:16]}..."
    )
    return _bundle_cache


def get_bundle_hash() -> str | None:
    """Return the current bundle's SHA-256 hash, or None if no bundle exists."""
    result = load_bundle()
    return result[1] if result else None


@router.get("/check", name="spaceos.check")
async def ota_check(
    request: Request,
    hash: str = Query("", description="SHA-256 of the board's current bundle"),
    x_board_id: str = Header(None, alias="X-Board-Id"),
    x_board_secret: str = Header(None, alias="X-Board-Secret"),
):
    """
    OTA update check endpoint for SpaceOS boards.

    The board sends its current bundle hash. The server compares it against the
    hash of spaceos-update.bin. If they differ (and OTA is enabled for this board),
    the server responds with 200 + the full signed bundle. Otherwise 204.

    Authentication: X-Board-Id (board UUID) + X-Board-Secret (raw secret key).
    """
    if not x_board_id or not x_board_secret:
        return Response(status_code=401)

    base_client = request.app.state.get_base_client()

    try:
        board = await q.selectBoardBySecretKey(base_client, board_id=UUID(x_board_id))
    except Exception:
        board = None

    if not board or not board.secret_key_hash:
        return Response(status_code=403)

    if not check_password_hash(board.secret_key_hash, x_board_secret):
        return Response(status_code=403)

    # Respect per-board OTA opt-out (field may not exist until queries are regenerated)
    ota_enabled = getattr(board, "ota_updates_enabled", True)
    if ota_enabled is None:
        ota_enabled = True
    if not ota_enabled:
        logger.info(f"OTA disabled for board {x_board_id[:8]}")
        return Response(status_code=204)

    bundle = load_bundle()
    if bundle is None:
        return Response(status_code=204)

    bundle_bytes, bundle_hash = bundle

    if hash and hash == bundle_hash:
        return Response(status_code=204)

    logger.info(
        f"Sending OTA bundle to board {x_board_id[:8]} "
        f"(board_hash={hash[:12] if hash else 'none'}, "
        f"bundle_hash={bundle_hash[:12]})"
    )
    return Response(
        content=bundle_bytes,
        media_type="application/octet-stream",
        status_code=200,
    )
