"""Native 22-slot presets, validated against the role's learned skills and unlocks.

The default arguments preserve the original level-one Elsword fixture;
runtime callers supply the current character and native skill-tree results.
"""
import struct

INITIAL_SKILLS=(21000,21200)
SLOT_COUNT=22
DEFAULT_SLOTS=INITIAL_SKILLS+(0,)*(SLOT_COUNT-len(INITIAL_SKILLS))

def validate_slots(slots,allowed=INITIAL_SKILLS,character=None):
    slots=tuple(slots)
    if len(slots)!=SLOT_COUNT or any(type(v) is not int or v not in (0,*allowed) for v in slots):
        raise ValueError('Invalid skill preset')
    occupied=[v for v in slots if v]
    if len(set(occupied))!=len(occupied):raise ValueError('Duplicate equipped skill')
    from els_server.domain.skill_expansion import unlocked_indices
    if any(v for i,v in enumerate(slots) if i not in unlocked_indices(character)):
        raise ValueError('Locked skill slot')
    from els_server.domain.role_progression import slot_accepts
    if any(v and not slot_accepts(i,v) for i,v in enumerate(slots)):
        raise ValueError('Skill does not belong to this slot type')
    return slots

def encode_slots(slots,allowed=INITIAL_SKILLS,character=None):
    return struct.pack('>22i',*validate_slots(slots,allowed,character))

def decode_slots(payload,allowed=INITIAL_SKILLS,character=None):
    if len(payload)!=88:raise ValueError('Invalid saved skill slots size')
    return validate_slots(struct.unpack('>22i',payload),allowed,character)

def record(skill, level=1):
    # CD5BB0: id, level, int metadata, byte metadata. Original 848860
    # consumes id/level for learned data; 848ec0 consumes the preset slots.
    if type(level) is not int or not 1<=level<=255:raise ValueError('Skill rank bound')
    return struct.pack('>iBiB',skill,level if skill else 0,0,0)

def equip_request(payload,slots,allowed=INITIAL_SKILLS,character=None):
    # Pinned DX11: 9B54C0 sends two int32s; 9B5750 consumes
    # result,index,id,otherIndex,id and applies through 8F8560.
    if len(payload)!=8:raise ValueError('Invalid equip request size')
    index,skill=struct.unpack('>ii',payload)
    from els_server.domain.skill_expansion import unlocked_indices
    if index not in unlocked_indices(character) or skill not in (0,*allowed):
        raise ValueError('Unsupported skill or locked slot')
    from els_server.domain.role_progression import slot_accepts
    if not slot_accepts(index,skill):raise ValueError('Skill slot type mismatch')
    updated=list(validate_slots(slots,allowed,character));other=-1;other_skill=0
    if skill and updated[index]!=skill and skill in updated:
        other=updated.index(skill);other_skill=updated[index];updated[other]=other_skill
    updated[index]=skill
    return validate_slots(updated,allowed,character),struct.pack('>5i',0,index,skill,other,other_skill)

def preset_payload(slots=DEFAULT_SLOTS,allowed=INITIAL_SKILLS,character=None):
    slots=validate_slots(slots,allowed,character)
    from els_server.domain.skill_traits import map_wire
    tail=struct.pack('>II',0,0)
    if character is not None:
        from els_server.domain.boosting_2026_force_equipment import vectors
        tail=vectors(character)
    return struct.pack('>I',22)+b''.join(record(v) for v in slots)+map_wire(character)+tail


def initialization_payload(slots=DEFAULT_SLOTS,uid=1001,allowed=INITIAL_SKILLS,learned_ranks=None,character=None):
    slots=validate_slots(slots,allowed,character)
    if (character or {}).get('ordinary_skill_pages',{}).get('count',1)>1:
        from els_server.domain.ordinary_skill_pages import initialization
        ranks={v:1 for v in allowed} if learned_ranks is None else learned_ranks
        return initialization(slots,uid,allowed,ranks,character)
    u32=lambda n:struct.pack('>I',n)
    from els_server.domain.skill_traits import map_wire
    preset=preset_payload(slots,allowed,character)
    ranks={v:1 for v in allowed} if learned_ranks is None else learned_ranks
    learned=u32(len(ranks))+b''.join(record(v,level) for v,level in ranks.items())
    from els_server.domain.skill_unlocks import ids_wire
    # 13A34F0's final DAED10 int vector -> 8F74B0 replaces manager+B0.
    return struct.pack('>Q',uid)+u32(1)+b'\0'+preset+learned+u32(0)*2+b'\0'+u32(0)*2+b'\1\1'+ids_wire(character)
