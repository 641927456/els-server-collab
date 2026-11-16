"""Straight-line KL82 registration chunks for the qualified original client VM.

Does not patch an original archive. The native registrars consume these tables
once during the existing signed component's startup callback.
"""
import struct


def uleb(n):
    out = bytearray()
    while n >= 128:
        out.append((n & 127) | 128)
        n >>= 7
    return bytes(out + bytes([n]))


def registration_chunk(calls):
    strings, numbers, code = [], [], bytearray()
    high = 0

    def index(pool, value):
        if value not in pool:
            pool.append(value)
        return pool.index(value)

    def ad(op, a, d):
        nonlocal high
        if not (0 <= a < 255 and 0 <= d < 65536):
            raise ValueError('KL register/constant extent')
        high = max(high, a)
        code.extend(struct.pack('<BBH', op, a, d))

    def abc(op, a, b, c):
        code.extend(bytes((op, a, c, b)))

    def value(reg, item):
        if isinstance(item, dict):
            ad(0x3c, reg, 0)
            for key, child in item.items():
                value(reg + 1, key)
                value(reg + 2, child)
                abc(0x44, reg + 2, reg, reg + 1)
        elif isinstance(item, str):
            ad(0x16, reg, index(strings, item))
        elif item is None or type(item) is bool:
            ad(0x1a, reg, 0 if item is None else 2 if item else 1)
        elif type(item) is int and -32768 <= item <= 32767:
            ad(0x18, reg, item & 65535)
        elif type(item) in (int, float):
            ad(0x19, reg, index(numbers, item))
        else:
            raise TypeError(item)

    for global_name, method, table in calls:
        if method is None:
            ad(0x3e, 0, index(strings, global_name))
            value(2, table)
            code.extend(bytes((0x2e, 0, 2, 1)))
        else:
            ad(0x3e, 2, index(strings, global_name))
            ad(0x16, 1, index(strings, method))
            abc(0x40, 0, 2, 1)
            value(3, table)
            code.extend(bytes((0x2e, 0, 3, 1)))
    code.extend(bytes((0x4b, 0, 1, 0)))
    constants = b''.join(uleb(len(s.encode('utf8')) + 5) + s.encode('utf8')
                         for s in reversed(strings))
    numeric = bytearray()
    for n in numbers:
        if type(n) is int and -2**31 <= n < 2**31:
            numeric.extend(uleb((n & 0xffffffff) << 1))
        else:
            lo, hi = struct.unpack('<II', struct.pack('<d', n))
            numeric.extend(uleb((lo << 1) | 1) + uleb(hi))
    body = (bytes((3, 0, high + 1, 0)) + uleb(len(strings)) + uleb(len(numbers))
            + uleb(len(code) // 4) + code + constants + numeric)
    return b'\x1bKL\x82\x0a' + uleb(len(body)) + body + b'\0'
