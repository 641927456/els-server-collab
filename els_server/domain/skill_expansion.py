"""Ordinary expansion ownership and stage-based transcendence skill positions.

200880's immutable native description explicitly grants Q/W/E/R on purchase.
12F -> 9B8B50 consumes UID, key, state, date, permanent flag. The role DTO
14E/DC vector carries key,state,date and is consumed by 87A6E0/8FAA70.
"""
import struct
from els_server.protocol.protocol_codec import Event

ORDINARY_PRODUCT=200880
ORDINARY_SKU=1200000000+ORDINARY_PRODUCT


def expanded(character):
    value=(character or {}).get('skill_row_expanded',False)
    if type(value) is not bool:raise ValueError('Invalid skill row entitlement')
    return value


def unlocked_indices(character=None):
    # 23073C0 + native SKILL_SLOT_TYPE: A=0..3, B=5..8;
    # 4 and 9 are the two transcendence positions (36C2E60).
    ordinary=(0,1,2,3,5,6,7,8) if expanded(character) else (0,1,2,3)
    from els_server.domain.skill_unlocks import unsealed_skills
    from els_server.game_data import client_data
    if character and any(client_data().skill(s)['m_eType']==13 for s in unsealed_skills(character)):
        ordinary=(*ordinary,20)
    if character and (character.get('transcendence') or character.get('master')):
        from els_server.domain.character_rules import CLASSES
        # 36C2E60 unlocks both TC positions for unit+5C > 0;
        # 189DDF0's slot 9 selection also uses this stage, not expansion key 1.
        # Stored stages must still belong to a second/third-job character.
        if CLASSES[character['unit_class']]['stage']>=2:
            special=(21,) if character.get('master') and CLASSES[character['unit_class']]['stage']==3 else ()
            return tuple(sorted((*ordinary,4,9,*special)))
    return ordinary


def records(character=None):
    # Preserve the legacy empty vector until this character owns expansion.
    if not expanded(character):return bytes(4)
    # Native role initialization reads both indices 0 and 1. Key 0 is the
    # ordinary expansion; preserve key 1 as zero until its use is proven.
    return struct.pack('>IiiIiiI',2,0,2,0,1,0,0)


def notice(uid,character):
    if not expanded(character):raise ValueError('Expansion notice without entitlement')
    return Event(0x201,kind=0x12f,payload=struct.pack('>QiiIB',uid,0,2,0,1))
