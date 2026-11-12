"""Install the ERP book inventory action at the existing DX11 native-ready point."""
import hashlib
import json
from pathlib import Path

EXE_SHA = '6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA = 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'


def compose(snapshot, executable_sha256, trace):
    if executable_sha256 != EXE_SHA or hashlib.sha256(snapshot).hexdigest() != IMAGE_SHA:
        raise ValueError('ERP book use client identity mismatch')
    anchor = '  clearInterval(timer);\n'
    if trace.count(anchor) != 1:
        raise ValueError('ERP book use native-ready anchor')
    sites = {
        0x220EBD0: 16, 0x221CE51: 13, 0x2217E6B: 48, 0x2260FD0: 16,
        0x152210: 8, 0x3FA02D0: 2, 0x7EEA50: 8, 0x197F500: 8, 0x197F660: 8,
    }
    pins = {rva: snapshot[rva:rva + size].hex() for rva, size in sites.items()}
    support = Path(__file__).with_suffix('.js').read_text(encoding='utf8')
    marker = '__ERP_BOOK_USE_PINS__'
    if support.count(marker) != 1 or pins[0x3FA02D0] != '0000':
        raise ValueError('ERP book use native contract')
    return support.replace(marker, json.dumps(pins)) + '\n' + trace.replace(
        anchor, anchor + '  installElsResonanceBookUse();\n',
    )
