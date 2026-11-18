"""Current-build 219/21A item use and 29F career notification."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import empty_record,record
from els_server.domain.skill_state import record as skill_record

def use_request(payload):
    # C595C0: item UID, optional target UID, two ints, wstring, bool.
    # Career consumables use no secondary item, string or extra parameters.
    if not isinstance(payload,bytes) or len(payload)!=29:raise ValueError('Career use request length')
    uid,target,a,b,n,flag=struct.unpack('>QQiiIB',payload)
    if not 0<uid<2**63 or target or a or b or n or flag:raise ValueError('Unsupported career item use parameters')
    return uid

def use_ack(changes=(),template=0,ed=0,result=0):
    # 234B140: result, inventory delta, three ints, ED and reserved uint64.
    delta=struct.pack('>I',len(changes))+b''.join(empty_record(*pos) if item is None else record(item) for pos,item in changes)
    return Event(0x201,kind=0x21a,payload=struct.pack('>i',result)+delta+struct.pack('>iiiQQ',template,0,0,ed,0))

def career_notice(character,location,slots,economy,items):
    from els_server.protocol.local_messages import character_unit
    from els_server.domain.skill_rules import learned_skills
    # B9C380 / kind29F: complete unit, learned skills (DAF5B0), int vector,
    # quest vector (DB60F0), quest-state vector (DD6E80). No GM acknowledgement.
    from els_server.domain.skill_unlocks import ids_wire
    ranks=learned_skills(character)
    body=character_unit(location,True,slots,economy,items,character)
    body+=struct.pack('>I',len(ranks))+b''.join(skill_record(v,level) for v,level in ranks.items())+ids_wire(character)+bytes(8)
    return Event(0x201,kind=0x29f,payload=body)

def stage_notice(character):
    from els_server.domain.character_rules import transcendental_stage
    return Event(0x201,kind=0x59f,payload=struct.pack('>ii',0,transcendental_stage(character)))


def current_skill_notices(character,slots,*,rebuild=True):
    """Original446 current skill-class/ranks/seals/Artifact, then saved Master slot.

    BB6750 replaces the learned and owned-unsealed collections, refreshes both
    skill trees and applies Artifact through8A1310. It does not run29F's ordinary
    career auto-entry path. The two i32 compatibility fields are deserialized
    but otherwise unused by the pinned consumer. Keep their existing zero form.
    """
    from els_server.domain.character_rules import validate_career_state,artifact_wire
    from els_server.domain.skill_rules import learned_skills,equippable_skills
    from els_server.domain.skill_state import validate_slots
    from els_server.domain.skill_unlocks import ids_wire
    from els_server.protocol.protocol_codec import encode_event
    validate_career_state(character)
    slots=validate_slots(slots,equippable_skills(character),character)
    ranks=learned_skills(character)
    body=struct.pack('>HiiI',character['unit_class'],0,0,len(ranks))
    body+=b''.join(skill_record(skill,rank)for skill,rank in ranks.items())
    body+=ids_wire(character)+artifact_wire(character)
    if type(rebuild)is not bool:raise ValueError('Current skill refresh mode')
    if rebuild:
        # Original446 includes native Master auto-equipping. Use it only for
        # first same-class stage entry, before a pre-existing Master choice.
        events=[Event(0x201,kind=0x446,payload=body)]
    else:
        # Original131 updates current ranks/seals without446's auto-selection.
        # The caller's29F/D9/F5 already restores current career/Artifact data.
        ranks_wire=struct.pack('>iI',0,len(ranks))
        ranks_wire+=b''.join(skill_record(skill,rank)for skill,rank in ranks.items())
        # A current snapshot is not a new seal grant. Original131's ID tail
        # inserts seals and opens acquisition popups; existing ownership is
        # already current after29F/initial loading. Do not replay those events.
        events=[Event(0x201,kind=0x131,payload=ranks_wire+struct.pack('>I',0))]
    if character['master']:
        events.append(Event(0x201,kind=0x123,payload=struct.pack('>5i',0,21,slots[21],-1,0)))
    for event in events:encode_event(event)
    from els_server.domain.native_skill_production import record as record_native_skill
    return [record_native_skill(event,character.get('uid'))if event.kind in(0x131,0x123)else event for event in events]
