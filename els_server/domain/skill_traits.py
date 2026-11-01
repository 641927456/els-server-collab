"""Native skill-note pairs and level gates, read from the pinned client."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.protocol.protocol_codec import Event

# 99CD8F constructor, owned-client passive definition read and actual dialog.
RESET_ED=500000


@functools.lru_cache(maxsize=1)
def catalog():
    p=Path(__file__).resolve().parents[1]/'data/skill_traits.json'
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='40c896f6af9c508689d2680a984ee784eb60c1013c534150388b8470001ee97b':raise ValueError('Skill trait definition checksum')
    data=json.loads(raw)
    from els_server.game_data import CLIENT_SHA
    from els_server.domain.character_rules import CLASSES
    if data['client_sha256']!=CLIENT_SHA or len(data['rows'])!=7974:raise ValueError('Skill trait definition identity')
    rules={}
    for r in data['rows']:
        c,s,n,l=(r[k] for k in ('unit_class','skill_id','note_id','required_level'))
        if c not in CLASSES or type(s) is not int or s<1 or n not in range(1,23) or l not in (20,40,70,99):raise ValueError('Skill trait definition bound')
        pair=rules.setdefault((c,s),{})
        if n in pair:raise ValueError('Duplicate native skill trait')
        pair[n]=l
    if {c for c,s in rules}!=set(CLASSES) or any(len(p)!=2 or len(set(p.values()))!=1 for p in rules.values()):raise ValueError('Native trait pair coverage')
    return rules


def bases(character):
    from els_server.domain.skill_rules import learned_skills
    from els_server.game_data import client_data
    result={};data=client_data()
    for sid in learned_skills(character):
        base=sid;seen=set()
        while data.skill(base).get('m_DeleteSkillIDByUpgrade'):
            if base in seen:raise ValueError('Cyclic trait skill upgrade')
            seen.add(base);base=data.skill(base)['m_DeleteSkillIDByUpgrade']
        result[sid]=base;result[base]=base
    return result


def validate(character,skill,note):
    if type(skill) is not int or type(note) is not int:raise ValueError('Skill trait identity')
    base=bases(character).get(skill)
    required=catalog().get((character['unit_class'],base),{}).get(note)
    if required is None or character['level']<required:raise ValueError('Unlearned, unavailable or locked skill trait')
    return base


def visible(character,saved):
    allowed=bases(character);rules=catalog();result={}
    for skill,note in saved.items():
        required=rules.get((character['unit_class'],skill),{}).get(note)
        if skill in allowed and required is not None and character['level']>=required:result[skill]=note
    return result


def map_wire(character=None):
    saved=(character or {}).get('skill_traits',{})
    if not saved:return bytes(4)
    traits=visible(character,saved)
    return struct.pack('>I',len(traits))+b''.join(struct.pack('>ii',s,n) for s,n in sorted(traits.items()))


def request(payload):
    # C53870 writes exactly two int32 values. BC2930 reads result,
    # original skill, note, then active preset byte from response 55E.
    if len(payload)!=8:raise ValueError('Skill trait request size')
    skill,note=struct.unpack('>ii',payload)
    if skill<=0 or not 1<=note<=22:raise ValueError('Skill trait request identity')
    return skill,note


def acknowledgement(skill=0,note=0,result=0,*,page=1):
    # 55B advertises active preset 1; BC2930 compares this one-based value
    # against unit+7F8 before applying the choice.
    if type(page)is not int or not 1<=page<=255:raise ValueError('Skill trait page')
    return Event(0x201,kind=0x55e,payload=struct.pack('>iiiB',result,skill,note,page))


def reset_request(payload):
    # C53BE0: original skill, note, optional scroll UID, use-ED boolean.
    if len(payload)!=17:raise ValueError('Skill trait reset size')
    skill,note,item_uid,use_ed=struct.unpack('>iiQB',payload)
    # The pinned running client registers no removable memo item IDs.
    if skill<=0 or not 1<=note<=22 or item_uid or use_ed!=1:raise ValueError('Unsupported trait reset payment')
    return skill,note


def reset_acknowledgement(skill=0,note=0,ed=0,result=0):
    # BC32D0: four ints, byte, DD46E0 inventory vector, DAF1D0 UID/bool
    # vector, boolean, ED, then DB3D10's fixed optional record.
    tail=struct.pack('>IBiQQB',0,2,0,0,0,0)
    body=struct.pack('>iiiiBIIBQ',result,0,skill,note,0,0,0,int(result==0),ed)+tail
    return Event(0x201,kind=0x560,payload=body)
