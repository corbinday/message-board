#!/usr/bin/env python3
"""
scripts/sign_spaceos.py — SpaceOS OTA bundle signing tool.

Usage:
    # Generate a new Ed25519 keypair (run once):
    python scripts/sign_spaceos.py --generate-key

    # Sign a release (private key from a PEM file or raw 32-byte hex seed):
    python scripts/sign_spaceos.py --key /path/to/private.pem
    python scripts/sign_spaceos.py --key /path/to/seed.hex

    # Sign a release using a PEM stored in 1Password (uses desktop app auth):
    python scripts/sign_spaceos.py --1password "op://VaultName/ItemName/FieldName" --account your-account-name

    For 1Password auth, ensure the 1Password desktop app is running and
    "Integrate with other apps" is enabled under Settings → Developer.
    You will be prompted to approve access via the desktop app.

The signed bundle (spaceos-update.bin) is written to the project root and
should be committed to the repo. The server serves it as-is; it never sees
the private key.

Requires: pip install cryptography onepassword-sdk
"""

import argparse
import asyncio
import hashlib
import os
import struct
import sys
from pathlib import Path

# Files excluded from the OTA bundle — immutable on the board
EXCLUDED = frozenset({"main.py", "update_key.py", "secrets.py", "os_hash", ".updating"})

SPACE_OS_DIR = Path(__file__).parent.parent / "space-os"
OUTPUT_FILE = Path(__file__).parent.parent / "spaceos-update.bin"


# ---------------------------------------------------------------------------
# Bundle building
# ---------------------------------------------------------------------------


def build_payload(space_os_dir: Path) -> bytes:
    """
    Collect all updatable files and pack them into the bundle payload.

    Format:
        [4 bytes: file count, big-endian uint32]
        for each file (sorted by name for reproducibility):
            [2 bytes: filename length, big-endian uint16]
            [N bytes: filename (UTF-8 basename)]
            [4 bytes: file content length, big-endian uint32]
            [M bytes: file content]
    """
    files = []
    for path in sorted(space_os_dir.iterdir()):
        if (
            path.is_file()
            and path.name not in EXCLUDED
            and not path.name.startswith(".")
        ):
            content = path.read_bytes()
            files.append((path.name, content))
            print(f"  + {path.name} ({len(content):,} bytes)")

    if not files:
        print("ERROR: No updatable files found in space-os/", file=sys.stderr)
        sys.exit(1)

    parts = [struct.pack(">I", len(files))]
    for name, content in files:
        name_bytes = name.encode("utf-8")
        parts.append(struct.pack(">H", len(name_bytes)))
        parts.append(name_bytes)
        parts.append(struct.pack(">I", len(content)))
        parts.append(content)

    return b"".join(parts)


# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------


def _load_private_key_from_bytes(key_data: bytes):
    """
    Parse an Ed25519 private key from raw bytes (PEM or hex seed).
    Returns a (sign_fn, pub_bytes) tuple.
    """
    try:
        from cryptography.hazmat.primitives.serialization import (
            load_pem_private_key,
            Encoding,
            PublicFormat,
        )
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        print(
            "ERROR: 'cryptography' package not installed.\n"
            "Install with: pip install cryptography",
            file=sys.stderr,
        )
        sys.exit(1)

    private_key = None

    # Try PEM first
    if b"-----" in key_data:
        try:
            pk = load_pem_private_key(key_data, password=None)
            if not isinstance(pk, Ed25519PrivateKey):
                print("ERROR: PEM key is not Ed25519.", file=sys.stderr)
                sys.exit(1)
            private_key = pk
        except Exception as e:
            print(f"ERROR loading PEM key: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Try raw hex seed (32 bytes → 64 hex chars)
        try:
            seed = bytes.fromhex(key_data.decode().strip())
            if len(seed) != 32:
                raise ValueError(f"Expected 32-byte seed, got {len(seed)} bytes")
            private_key = Ed25519PrivateKey.from_private_bytes(seed)
        except Exception as e:
            print(f"ERROR loading hex seed key: {e}", file=sys.stderr)
            sys.exit(1)

    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    def sign(payload: bytes) -> bytes:
        return private_key.sign(payload)

    return sign, pub_bytes


def _load_private_key(key_path: Path):
    """Load an Ed25519 private key from a PEM file or a raw hex-encoded seed file."""
    return _load_private_key_from_bytes(key_path.read_bytes())


async def _resolve_key_from_1password(secret_ref: str, account_name: str) -> bytes:
    """
    Load a PEM key from 1Password using desktop app authentication.
    Requires the 1Password desktop app to be running with
    "Integrate with other apps" enabled under Settings → Developer.

    Secret ref format: op://VaultName/ItemName/FieldName
    """
    try:
        from onepassword.client import Client, DesktopAuth
    except ImportError:
        print(
            "ERROR: 'onepassword-sdk' not installed.\n"
            "Install with: pip install onepassword-sdk",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Connecting to 1Password desktop app...")
    print("You may be prompted to approve access in the 1Password app.")

    try:
        client = await Client.authenticate(
            auth=DesktopAuth(account_name=account_name),
            integration_name="SpaceOS Signing Tool",
            integration_version="v1.0.0",
        )
    except Exception as e:
        print(
            f"ERROR: Could not connect to 1Password desktop app: {e}\n"
            "Make sure the 1Password app is running and 'Integrate with other apps'\n"
            "is enabled under Settings → Developer.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Fetching key from 1Password ({secret_ref})...")
    try:
        pem_str = await client.secrets.resolve(secret_ref)
    except Exception as e:
        print(f"ERROR: Could not resolve secret reference: {e}", file=sys.stderr)
        sys.exit(1)

    return pem_str.encode("utf-8")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_generate_key(args):
    """Generate a new Ed25519 keypair and print instructions."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PrivateFormat,
            PublicFormat,
            NoEncryption,
        )
    except ImportError:
        print("ERROR: pip install cryptography", file=sys.stderr)
        sys.exit(1)

    private_key = Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

    print("\n=== Ed25519 Keypair Generated ===\n")
    print("PRIVATE KEY (PEM) — store in your password manager, never commit:")
    print(pem.decode())
    print("PUBLIC KEY (hex) — copy into space-os/update_key.py:")
    print(pub_bytes.hex())
    print(f"\nIn update_key.py, set:")
    print(f"  PUBLIC_KEY = bytes.fromhex('{pub_bytes.hex()}')")
    print("\nTo sign a release with a local key file:")
    print("  python scripts/sign_spaceos.py --key /path/to/private.pem")
    print("\nTo sign a release using 1Password:")
    print(
        '  python scripts/sign_spaceos.py --1password "op://VaultName/ItemName/FieldName" --account your-account-name'
    )


def cmd_sign(args):
    """Bundle and sign the space-os/ files."""
    if not SPACE_OS_DIR.is_dir():
        print(
            f"ERROR: space-os/ directory not found at {SPACE_OS_DIR}", file=sys.stderr
        )
        sys.exit(1)

    # Resolve the private key — from 1Password or from a local file
    if args.onepassword:
        if not args.account:
            print(
                "ERROR: --account is required when using --1password.\n"
                "This is your account name as it appears in the top-left of the 1Password app.",
                file=sys.stderr,
            )
            sys.exit(1)
        key_data = asyncio.run(
            _resolve_key_from_1password(args.onepassword, args.account)
        )
        sign, pub_bytes = _load_private_key_from_bytes(key_data)
    elif args.key:
        key_path = Path(args.key)
        if not key_path.exists():
            print(f"ERROR: Key file not found: {key_path}", file=sys.stderr)
            sys.exit(1)
        sign, pub_bytes = _load_private_key(key_path)
    else:
        print(
            "ERROR: Provide --key <path> or --1password <secret-ref>", file=sys.stderr
        )
        sys.exit(1)

    print(f"Building bundle from {SPACE_OS_DIR}/")
    payload = build_payload(SPACE_OS_DIR)
    print(
        f"Bundle payload: {len(payload):,} bytes, {struct.unpack('>I', payload[:4])[0]} files"
    )

    print("Signing...")
    signature = sign(payload)
    assert len(signature) == 64

    bundle = signature + payload
    bundle_hash = hashlib.sha256(bundle).hexdigest()

    OUTPUT_FILE.write_bytes(bundle)

    print(f"\n{'=' * 50}")
    print(f"Output:      {OUTPUT_FILE}")
    print(f"Total size:  {len(bundle):,} bytes")
    print(f"SHA-256:     {bundle_hash}")
    print(f"Public key:  {pub_bytes.hex()}")
    print(f"{'=' * 50}")
    print(f"\nCommit spaceos-update.bin to the repo to publish this release.")
    print(f"Verify update_key.py contains:")
    print(f"  PUBLIC_KEY = bytes.fromhex('{pub_bytes.hex()}')")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="SpaceOS OTA bundle signing tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Generate a new Ed25519 keypair and print instructions",
    )
    parser.add_argument(
        "--key",
        metavar="PATH",
        help="Path to Ed25519 private key (PEM or raw 32-byte hex seed)",
    )
    parser.add_argument(
        "--1password",
        dest="onepassword",
        metavar="SECRET_REF",
        help="1Password secret reference URI (e.g. op://MyVault/SpaceOS Key/private key)",
    )
    parser.add_argument(
        "--account",
        metavar="ACCOUNT_NAME",
        help="Your 1Password account name as shown in the top-left of the desktop app (required with --1password)",
    )

    args = parser.parse_args()

    if args.generate_key:
        cmd_generate_key(args)
    elif args.key or args.onepassword:
        cmd_sign(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
