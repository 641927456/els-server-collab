"""Suppress startup page drawing while retaining the native startup lifecycle."""
from pathlib import Path
import hashlib
import json

EXE_SHA = '6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA = 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
SITES = (0xb76c20, 0xb76c60, 0x133daf0, 0x30f2050, 0x30f2090, 0x30f20c0,
         0x454200, 0x4542b0, 0x454330, 0x4546c0, 0x74ecf0)


def compose(snapshot, executable_sha256, template):
    if executable_sha256 != EXE_SHA or hashlib.sha256(snapshot).hexdigest() != IMAGE_SHA:
        raise ValueError('Startup visibility client identity mismatch')
    source = Path(__file__).with_suffix('.js').read_text(encoding='utf8')
    if source.count('__STARTUP_UI_PINS__') != 1:
        raise ValueError('Startup visibility source contract')
    source = source.replace('__STARTUP_UI_PINS__', json.dumps({
        r: snapshot[r:r + 32].hex() for r in SITES}))
    changes = (
        (("if(Object.entries(verifiedPrefixes).every(([r,h])=>Array.from(new Uint8Array("
          "game.base.add(Number(r)).readByteArray(8)),v=>v.toString(16).padStart(2,'0')).join('')===h)){"),
         ("if(Object.entries(verifiedPrefixes).every(([r,h])=>Array.from(new Uint8Array("
          "game.base.add(Number(r)).readByteArray(8)),v=>v.toString(16).padStart(2,'0')).join('')===h)"
          "&&elsStartupVisibilityReady()){ ")),
        ("  clearInterval(timer);\n", "  clearInterval(timer);\n  installElsStartupVisibility();\n"),
        ("onEnter(a){this.state=a[0];},onLeave(){const p=this.state;",
         "onEnter(a){finishElsStartupVisibility('character-selection');this.state=a[0];},onLeave(){const p=this.state;"),
    )
    for before, after in changes:
        if template.count(before) != 1:
            raise ValueError('Startup visibility parent composition anchor')
        template = template.replace(before, after)
    return source + '\n' + template
