# update_key.py - Ed25519 public key for OTA update verification
# IMMUTABLE — never included in OTA bundles, never updated remotely.
#
# To generate a keypair:
#   python scripts/sign_spaceos.py --generate-key
#
# Replace PUBLIC_KEY with the 32-byte raw public key bytes printed by the script.
# The private key stays in your password manager and is never committed to the repo.

PUBLIC_KEY = bytes(32)  # placeholder — replace with actual public key before deploying
