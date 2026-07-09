"""UUIDv7 (RFC 9562) — sortable IDs, per specs/03-design/08-data-model.md.

Python's stdlib `uuid` module doesn't gain `uuid7()` until 3.14; this repo
targets 3.11+ (dev Windows, prod aarch64 Linux), so we generate it by hand
rather than adding a dependency for 20 lines of bit-packing.
"""
import os
import time
import uuid


def uuid7() -> uuid.UUID:
    unix_ts_ms = int(time.time() * 1000)
    rand = os.urandom(10)

    b = bytearray(16)
    b[0:6] = unix_ts_ms.to_bytes(6, "big")
    b[6] = 0x70 | (rand[0] & 0x0F)  # version 7
    b[7] = rand[1]
    b[8] = 0x80 | (rand[2] & 0x3F)  # variant 10
    b[9:16] = rand[3:10]
    return uuid.UUID(bytes=bytes(b))


def new_id() -> str:
    return str(uuid7())
