"""Compose the native578 guide lifecycle support; no EXE/KOM replacement."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
SITES=(0x2f926a0,0x4fed20,0x2f98010,0x7b2f20,0x7e7050,0x4ab6d0,0x4b45b0)
RANGES=((47247360, 47248291, 47247360), (47246384, 47247347, 47246384), (49868816, 49869881, 49868816), (49869888, 49870953, 49869888), (49870960, 49871859, 49870960), (49871872, 49872675, 49871872), (49872688, 49873622, 49872688), (49873632, 49874564, 49873632), (49874576, 49875555, 49874576), (49875568, 49876661, 49875568), (49876672, 49877765, 49876672), (49877776, 49878710, 49877776), (49878720, 49879622, 49878720), (49879632, 49880550, 49879632), (49891776, 49892708, 49891776), (49892720, 49893800, 49892720), (49893808, 49895379, 49893808), (49899216, 49900840, 49899216), (52218960, 52219296, 49871872))

def source(snapshot,executable_sha256):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Activity guide client identity mismatch')
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    if raw.count('__ACTIVITY_GUIDE_CONFIG__')!=1:raise ValueError('Activity guide source contract')
    config=dict(pins={r:snapshot[r:r+32].hex() for r in SITES},ranges=RANGES,requirements={1: [47247360], 2: [47246384, 49869888], 3: [49868816], 4: [49899216], 5: [49870960], 6: [49872688], 7: [49891776, 49892720], 8: [49878720], 9: [49893808, 49879632], 10: [49870960], 11: [49871872], 12: [49870960], 13: [49872688], 14: [49873632, 49874576, 49875568], 15: [49873632, 49874576, 49875568], 16: [49876672], 17: [49877776], 18: [49878720]})
    return raw.replace('__ACTIVITY_GUIDE_CONFIG__',json.dumps(config))

def compose(snapshot,executable_sha256,template):
    anchor='  clearInterval(timer);\n'
    if template.count(anchor)!=1:raise ValueError('Activity guide parent composition anchor')
    return source(snapshot,executable_sha256)+'\n'+template.replace(anchor,anchor+'  installElsActivityGuideLifecycle();\n')
