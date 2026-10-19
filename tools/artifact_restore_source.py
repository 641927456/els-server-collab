"""Pinned native scene adapter, loaded by the existing early client owner."""
import hashlib,json
from pathlib import Path
def bridge_source(image):
    assert hashlib.sha256(image).hexdigest()=='3cc9fca449c7a543957c5cdf439c7ba81323efd4a4b3fe577ed0ff0e954a820a'
    # Body guards avoid the already-installed startup observation trampolines.
    rvas=(0x682db0,0x30d0680,0x1310150)
    return (Path(__file__).with_name('local_artifact_restore.js').read_text('utf8')
            .replace('__ARTIFACT_PREFIXES__',json.dumps({r:image[r:r+8].hex() for r in rvas})))
