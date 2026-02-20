# ed25519.py - Ed25519 signature verification for MicroPython
# Based on RFC 8032 (https://datatracker.ietf.org/doc/html/rfc8032)
#
# Pure Python — verification is compute-intensive (~10–30s on RP2040).
# Requires uhashlib with SHA-512 support (standard on Pimoroni firmware).

import uhashlib

# Ed25519 field prime
_p = 2 ** 255 - 19
# Group order
_l = 2 ** 252 + 27742317777372353535851937790883648493
# Curve constant d = -121665/121666 mod p
_d = (-121665 * pow(121666, _p - 2, _p)) % _p
# sqrt(-1) mod p
_sqrt_m1 = pow(2, (_p - 1) // 4, _p)

# Base point G (extended coordinates: X, Y, Z, T where x=X/Z, y=Y/Z, T=X*Y/Z)
_G = None


def _sha512(data):
    h = uhashlib.sha512()
    h.update(data)
    return h.digest()


def _recover_x(y, sign):
    """Recover x coordinate from y and the sign bit."""
    if y >= _p:
        return None
    x2 = (y * y - 1) * pow(_d * y * y + 1, _p - 2, _p) % _p
    if x2 == 0:
        return 0 if not sign else None
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p != 0:
        x = x * _sqrt_m1 % _p
    if (x * x - x2) % _p != 0:
        return None
    if x & 1 != sign:
        x = _p - x
    return x


def _base_point():
    gy = 4 * pow(5, _p - 2, _p) % _p
    gx = _recover_x(gy, 0)
    return (gx, gy, 1, gx * gy % _p)


def _point_add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C = 2 * P[3] * Q[3] * _d % _p
    D = 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _p, G * H % _p, F * G % _p, E * H % _p)


def _point_mul(s, P):
    """Scalar multiplication using double-and-add."""
    Q = (0, 1, 1, 0)  # Identity element
    while s > 0:
        if s & 1:
            Q = _point_add(Q, P)
        P = _point_add(P, P)
        s >>= 1
    return Q


def _point_compress(P):
    zinv = pow(P[2], _p - 2, _p)
    x = P[0] * zinv % _p
    y = P[1] * zinv % _p
    result = bytearray(32)
    for i in range(32):
        result[i] = (y >> (8 * i)) & 0xFF
    if x & 1:
        result[31] |= 0x80
    return bytes(result)


def _point_decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _p)


def verify(public_key, message, signature):
    """
    Verify an Ed25519 signature.

    Args:
        public_key: 32-byte Ed25519 public key (bytes)
        message:    bytes to verify
        signature:  64-byte Ed25519 signature (bytes)

    Returns:
        True if the signature is valid, False otherwise.

    Note: This is a pure-Python implementation and may take 10–30 seconds
    on RP2040 hardware due to the large scalar multiplications.
    """
    global _G
    if _G is None:
        _G = _base_point()

    if len(public_key) != 32 or len(signature) != 64:
        return False

    A = _point_decompress(public_key)
    if A is None:
        return False

    Rs = signature[:32]
    R = _point_decompress(Rs)
    if R is None:
        return False

    s = int.from_bytes(signature[32:], "little")
    if s >= _l:
        return False

    h = int.from_bytes(_sha512(Rs + public_key + message), "little") % _l

    sB = _point_mul(s, _G)
    hA = _point_mul(h, A)
    # Negate hA to compute sB - hA
    hA_neg = ((-hA[0]) % _p, hA[1], hA[2], (-hA[3]) % _p)

    return _point_compress(_point_add(sB, hA_neg)) == _point_compress(R)
