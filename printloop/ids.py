# SPDX-License-Identifier: AGPL-3.0-only
"""IDs the server mints (§9): ULIDs (time + random, Crockford base32) and
the 4-character gate tokens."""
import secrets
import time

_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid(now=None):
    t = int((now if now is not None else time.time()) * 1000)
    r = secrets.randbits(80)
    v = (t << 80) | r
    return "".join(_B32[(v >> (5 * i)) & 31] for i in range(25, -1, -1))


def token(n=4):
    return "".join(secrets.choice(_B32) for _ in range(n))
