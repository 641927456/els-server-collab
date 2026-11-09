"""Pinned native scene adapter, loaded by the existing early client owner."""
import hashlib,json
from pathlib import Path
def bridge_source(image):
    assert hashlib.sha256(image).hexdigest()=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
    # Body guards avoid the already-installed startup observation trampolines.
    rvas=(0x682db0,0x30d0680,0x1310150)
    return (Path(__file__).with_name('local_artifact_restore.js').read_text('utf8')
            .replace('__ARTIFACT_PREFIXES__',json.dumps({r:image[r:r+8].hex() for r in rvas})))
