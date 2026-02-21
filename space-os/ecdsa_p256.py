# ed25519.py - ECDSA P-256 / SHA-256 signature verification for MicroPython
#
# Replaces the original Ed25519 implementation. Ed25519 requires SHA-512
# internally, which is absent from the Pimoroni Pico W firmware. ECDSA P-256
# uses SHA-256, available natively via uhashlib on all supported boards.
#
# Public key format:  64 bytes — raw X || Y, big-endian (no 0x04 prefix)
# Signature format:   64 bytes — raw R || S, big-endian
# Hash:               SHA-256 via uhashlib (C implementation, essentially instant)
#
# The two scalar multiplications in verify() are pure Python and still take
# ~10–20 s on RP2040, but that is unavoidable in any asymmetric scheme.

import uhashlib

# ---------------------------------------------------------------------------
# NIST P-256 (secp256r1) parameters
# ---------------------------------------------------------------------------
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_A = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFC  # = -3 mod p
_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5


# ---------------------------------------------------------------------------
# Jacobian projective coordinates  (X:Y:Z)  where affine x=X/Z², y=Y/Z³.
# Z==0 represents the point at infinity.
# ---------------------------------------------------------------------------


def _jdouble(X1, Y1, Z1):
    """Point doubling — uses the a=−3 shortcut valid for P-256."""
    if Z1 == 0:
        return (0, 1, 0)
    Y1sq = Y1 * Y1 % _P
    S = 4 * X1 * Y1sq % _P
    Z1sq = Z1 * Z1 % _P
    M = 3 * (X1 - Z1sq) * (X1 + Z1sq) % _P  # a=−3 optimisation
    X3 = (M * M - 2 * S) % _P
    Y3 = (M * (S - X3) - 8 * Y1sq * Y1sq) % _P
    Z3 = 2 * Y1 * Z1 % _P
    return (X3, Y3, Z3)


def _jadd(X1, Y1, Z1, X2, Y2, Z2):
    """Full Jacobian point addition (both points in projective coordinates)."""
    if Z1 == 0:
        return (X2, Y2, Z2)
    if Z2 == 0:
        return (X1, Y1, Z1)
    Z1sq = Z1 * Z1 % _P
    Z2sq = Z2 * Z2 % _P
    U1 = X1 * Z2sq % _P
    U2 = X2 * Z1sq % _P
    S1 = Y1 * Z2sq * Z2 % _P
    S2 = Y2 * Z1sq * Z1 % _P
    H = (U2 - U1) % _P
    R = (S2 - S1) % _P
    if H == 0:
        return _jdouble(X1, Y1, Z1) if R == 0 else (0, 1, 0)
    H2 = H * H % _P
    H3 = H * H2 % _P
    X3 = (R * R - H3 - 2 * U1 * H2) % _P
    Y3 = (R * (U1 * H2 - X3) - S1 * H3) % _P
    Z3 = H * Z1 * Z2 % _P
    return (X3, Y3, Z3)


def _jmul(k, Px, Py):
    """
    Scalar multiplication k*(Px,Py) using double-and-add.
    Returns affine (x, y) or None for the point at infinity.
    """
    Qx, Qy, Qz = 0, 1, 0  # accumulator — starts at infinity
    Rx, Ry, Rz = Px, Py, 1  # current bit-value of P in Jacobian
    while k:
        if k & 1:
            Qx, Qy, Qz = _jadd(Qx, Qy, Qz, Rx, Ry, Rz)
        Rx, Ry, Rz = _jdouble(Rx, Ry, Rz)
        k >>= 1
    if Qz == 0:
        return None
    Zinv = pow(Qz, _P - 2, _P)
    Zinv2 = Zinv * Zinv % _P
    return (Qx * Zinv2 % _P, Qy * Zinv2 * Zinv % _P)


# ---------------------------------------------------------------------------
# ECDSA P-256 / SHA-256 verification
# ---------------------------------------------------------------------------


def verify(public_key, message, signature):
    """
    Verify an ECDSA P-256 / SHA-256 signature.

    Args:
        public_key:  64-byte raw X || Y (big-endian, no 0x04 prefix)
        message:     bytes to verify
        signature:   64-byte raw R || S (big-endian)

    Returns:
        True if valid, False otherwise.
    """
    if len(public_key) != 64 or len(signature) != 64:
        return False

    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    if not (1 <= r < _N and 1 <= s < _N):
        return False

    Qx = int.from_bytes(public_key[:32], "big")
    Qy = int.from_bytes(public_key[32:], "big")

    h_obj = uhashlib.sha256()
    h_obj.update(message)
    e = int.from_bytes(h_obj.digest(), "big")

    w = pow(s, _N - 2, _N)  # modular inverse of s
    u1 = e * w % _N
    u2 = r * w % _N

    # X = u1·G + u2·Q
    P1 = _jmul(u1, _GX, _GY)
    P2 = _jmul(u2, Qx, Qy)

    if P1 is None:
        pt = P2
    elif P2 is None:
        pt = P1
    else:
        jx, jy, jz = _jadd(P1[0], P1[1], 1, P2[0], P2[1], 1)
        if jz == 0:
            return False
        Zinv = pow(jz, _P - 2, _P)
        Zinv2 = Zinv * Zinv % _P
        pt = (jx * Zinv2 % _P, jy * Zinv2 * Zinv % _P)

    if pt is None:
        return False

    return pt[0] % _N == r
