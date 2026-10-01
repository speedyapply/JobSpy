from __future__ import annotations

import base64
import functools
import secrets
import time

from jobspy.naukri.constant import nkparam_public_key


def _read_der(data: bytes, i: int) -> tuple[bytes, int]:
    """Returns the DER value at data[i] and the index after it."""
    length = data[i + 1]
    i += 2
    if length & 0x80:
        size = length & 0x7F
        length = int.from_bytes(data[i : i + size], "big")
        i += size
    return data[i : i + length], i + length


@functools.cache
def public_key() -> tuple[int, int]:
    key, _ = _read_der(base64.b64decode(nkparam_public_key), 0)
    _, i = _read_der(key, 0)
    bit_string, _ = _read_der(key, i)
    rsa_key, _ = _read_der(bit_string[1:], 0)
    modulus, i = _read_der(rsa_key, 0)
    exponent, _ = _read_der(rsa_key, i)
    return int.from_bytes(modulus, "big"), int.from_bytes(exponent, "big")


def generate_nkparam(page: str) -> str:
    """Naukri's request token: RSA (PKCS#1 v1.5) of "v0|<ms>|121_<page>"."""
    modulus, exponent = public_key()
    size = (modulus.bit_length() + 7) // 8
    message = f"v0|{int(time.time() * 1000)}|121_{page}".encode()
    padding = bytes(secrets.randbelow(255) + 1 for _ in range(size - 3 - len(message)))
    block = b"\x00\x02" + padding + b"\x00" + message
    cipher = pow(int.from_bytes(block, "big"), exponent, modulus)
    return base64.b64encode(cipher.to_bytes(size, "big")).decode()
