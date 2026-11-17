"""Install the pinned ownership predicate after the existing unpack/readiness gate."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent

def source(snapshot,digest):
    raw=(HERE/'quest_skill_ownership_hide.json').read_bytes()
    script=(HERE/'quest_skill_ownership_hide.js').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='2dfacb8996e64a94f932db3e8496d8d5189f39afe37901124d31404977192a88' or hashlib.sha256(script).hexdigest()!='d62e827a6a354baf671a6035256d018ae3bf080750d3af21cdd8cb75c9a2fdcf':raise ValueError('Quest ownership support identity')
    rules=json.loads(raw)
    if digest!=rules['executable_sha256']or hashlib.sha256(snapshot).hexdigest()!=rules['image_sha256']:raise ValueError('Quest ownership client identity')
    rva=rules['function_rva']
    if snapshot[rva:rva+16].hex()!=rules['prefix16']:raise ValueError('Quest ownership function identity')
    text=script.decode('utf8')
    if text.count('__RULES__')!=1:raise ValueError('Quest ownership source template')
    return text.replace('__RULES__',json.dumps(rules,separators=(',',':')))

def compose(snapshot,digest,parent):
    if hashlib.sha256(parent.replace('\r\n','\n').encode()).hexdigest()!='f8983fa04620c946ccbee9e607eb196172f8dde8925a66cabb1001b08041e54c':raise ValueError('Quest ownership parent changed; explicit merge required')
    anchor='  clearInterval(timer);\n  installElsResonanceBookUse();'
    parent=parent.replace('\r\n','\n')
    if parent.count(anchor)!=1:raise ValueError('Quest ownership readiness anchor')
    result=parent.replace(anchor,'  clearInterval(timer);\n  installElsQuestSkillOwnershipHide();\n  installElsResonanceBookUse();')
    return source(snapshot,digest)+'\n'+result
