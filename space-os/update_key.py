# update_key.py - ECDSA P-256 public key for OTA update verification
# IMMUTABLE — never included in OTA bundles, never updated remotely.
#
# To generate a new keypair:
#   python scripts/sign_spaceos.py --generate-key
#
# Replace PUBLIC_KEY with the 64-byte raw X||Y hex printed by that command.
# The private key stays in your password manager and is never committed.

PUBLIC_KEY = bytes.fromhex(
    "bfbf1db21b45aa4f4b0a5e4a848af813c5c81b9d555a1e276cd9b781d22124ca29d38caf8911c55449c318f213e92dc2a0d3d254a65070db51a044e907564811"
)
