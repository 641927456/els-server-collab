"""Prepare the process-lifetime native send lock, with immutable client pins.

Install before the result-report observer can call the original sender again.
The original EXE and all native serialization/encryption remain unchanged.
"""
from pathlib import Path
import hashlib,json

EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'

def source(snapshot,executable_sha256):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Native send serialization client identity')
    # Existing trace/CP observers own the entry; use untouched body anchors.
    anchors={0x682da0:16,0x683104:5,0x68318c:5,0x3b7d860:16,
             0x1271e60:4,0x3b817b0:4,0x6875a0:16,0x30d0680:8}
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    if raw.count('__SEND_SERIALIZATION_PINS__')!=1:
        raise ValueError('Native send serialization source anchor')
    return raw.replace('__SEND_SERIALIZATION_PINS__',json.dumps({r:snapshot[r:r+n].hex()for r,n in anchors.items()}))


def compose(snapshot,executable_sha256,template):
    # NativeFunction calls inside a JS onEnter can bypass that listener on
    # reentry. Acquire the lock BEFORE registering any such send observer.
    anchor='  clearInterval(timer);\n  installElsChallengeScrollSupport();'
    if template.count(anchor)!=1:
        raise ValueError('Native send serialization startup ordering')
    replacement='  clearInterval(timer);\n  prepareElsNativeSendSerialization()();\n  installElsChallengeScrollSupport();'
    from artifact_restore_source import bridge_source
    artifact=bridge_source(snapshot)
    # Keep all production sender observers in one Script realm. A separate
    # artifact Script would be a third physical Gum listener at this address.
    artifact_anchor='Interceptor.attach(arM.base.add(0x682d80),'
    if artifact.count(artifact_anchor)!=1:raise ValueError('Artifact sender observation anchor')
    artifact=artifact.replace(artifact_anchor,'elsObserveNativeSend(')
    field_anchor='Interceptor.attach(arM.base.add(0x30d0660),'
    if artifact.count(field_anchor)!=1:raise ValueError('Artifact field observation anchor')
    artifact=artifact.replace(field_anchor,'elsObserveNativeField(')
    from install_ed_shop_bridge import bridge_source as shop_source
    shop=shop_source(snapshot)
    field_anchor='Interceptor.attach(ebM.base.add(0x30d0660),'
    if shop.count(field_anchor)!=2:raise ValueError('Shop field observation count')
    shop=shop.replace(field_anchor,'elsObserveNativeField(')
    startup='  noahVerifiedSenderReady=true;'
    if template.count(startup)!=1:raise ValueError('Shared artifact startup anchor')
    result=template.replace(anchor,replacement).replace(startup,'  if(__ARTIFACT_RESTORE__)installElsSharedArtifactRestore();\n  if(__SHOP_BRIDGE__)installElsSharedShopBridge();\n'+startup)
    for text,count in [('Interceptor.attach(module.base.add(0x682d80),',2),('Interceptor.attach(game.base.add(0x682d80),',2)]:
        if result.count(text)!=count:raise ValueError('Shared sender observation count: '+text)
        result=result.replace(text,'elsObserveNativeSend(')
    field_anchor='Interceptor.attach(game.base.add(0x30d0660),'
    if result.count(field_anchor)!=2:raise ValueError('Main field observation count')
    result=result.replace(field_anchor,'elsObserveNativeField(')
    return source(snapshot,executable_sha256)+'\nfunction installElsSharedArtifactRestore(){\n'+artifact+'\n}\nfunction installElsSharedShopBridge(){\n'+shop+'\n}\n'+result
