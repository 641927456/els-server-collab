"""Pinned challenge-week comparison support, composed at native readiness."""
from pathlib import Path
import hashlib
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
def compose(snapshot,executable_sha256,template):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Challenge scroll client identity mismatch')
    anchor='  clearInterval(timer);\n'
    if template.count(anchor)!=1:raise ValueError('Challenge scroll native-ready anchor')
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    return raw+'\n'+template.replace(anchor,anchor+'  installElsChallengeScrollSupport();\n')
