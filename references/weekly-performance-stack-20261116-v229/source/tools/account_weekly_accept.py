"""Compose the account-weekly predicate into the existing readiness gate."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
PARENT_SHA='70d1af511f1578d2934db3969d6222c0feba8ddf63f89c13a7904c1ed256dc13'

def source(snapshot,digest):
    raw=(HERE/'account_weekly_accept.json').read_bytes()
    script=(HERE/'account_weekly_accept.js').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='d21403f87e6dadc188f38d3017b57687bfb10e960312441bbfa5cb254fe76f4b':
        raise ValueError('Account weekly rules identity')
    if hashlib.sha256(script).hexdigest()!='4bc66df57b9170a57741768ac09f234ba98a641596613ba7cc03a941dd19a64b':
        raise ValueError('Account weekly script identity')
    rules=json.loads(raw)
    if digest!=rules['executable_sha256']or hashlib.sha256(snapshot).hexdigest()!=rules['image_sha256']:
        raise ValueError('Account weekly client identity')
    for rva,prefix in rules['prefixes'].items():
        start=int(rva)
        if snapshot[start:start+16].hex()!=prefix:raise ValueError('Account weekly native prefix')
    text=script.decode('utf8')
    if text.count('__RULES__')!=1:raise ValueError('Account weekly source template')
    return text.replace('__RULES__',json.dumps(rules,separators=(',',':')))

def compose(snapshot,digest,parent):
    parent=parent.replace('\r\n','\n')
    if hashlib.sha256(parent.encode()).hexdigest()!=PARENT_SHA:
        raise ValueError('Account weekly parent changed; explicit merge required')
    anchor='  installElsQuestSkillOwnershipHide();\n'
    if parent.count(anchor)!=1:raise ValueError('Account weekly readiness anchor')
    return source(snapshot,digest)+'\n'+parent.replace(anchor,anchor+'  installElsAccountWeeklyAccept();\n')
