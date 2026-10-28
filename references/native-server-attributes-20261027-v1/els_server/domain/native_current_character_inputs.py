"""Read source context from the same field writer that emits the complete Unit.

This qualifies the full-character-copy boundary only. Independent world-manager,
Actor, alias, named-update and source-group lifecycles remain separate inputs;
an empty Unit field must not be used to clear those independent sources.
"""
import hashlib
import json
import struct
from els_server.domain.native_character_context import after_character_copy
from els_server.domain.native_resonance_source_groups import numeric_groups,progress_fields


def build(snapshot, *, previous_rank):
    from els_server.protocol.local_messages import character_unit_fields
    if type(snapshot)is not dict:
        raise ValueError('Same-generation native source snapshot required')
    keys={'owner','account_id','character','items','ordinary_slots','resonance','companions','world_effects','source_sha256'}
    if set(snapshot)!=keys:
        raise ValueError('Complete canonical native source families required')
    raw=json.dumps({k:v for k,v in snapshot.items()if k!='source_sha256'},
        ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
    if hashlib.sha256(raw).hexdigest()!=snapshot['source_sha256']:
        raise ValueError('Native source changed after capture')
    character=snapshot['character'];owner=snapshot['owner']
    if (type(owner)is not int or not 0<owner<2**64 or character['uid']!=owner
            or type(snapshot['items'])is not tuple or type(snapshot['ordinary_slots'])is not tuple):
        raise ValueError('Owned canonical native source identity required')
    fields=character_unit_fields(items=snapshot['items'],character=character,
        slots=snapshot['ordinary_slots'])
    mapping=dict(fields)
    if len(mapping)!=len(fields):
        raise ValueError('Duplicate original Unit source field')
    if (mapping['0x3fc']!=bytes(4)or len(mapping['0xb6'])!=28
            or mapping['0xb6']!=mapping['0xd2']):
        raise ValueError('Current full-copy named/base source needs qualification')
    base=struct.unpack('>7f',mapping['0xb6'])
    copied=after_character_copy(mapping['0x6a'],mapping['0x3c5'],previous_rank=previous_rank)
    title=struct.unpack('>i',mapping['0x307'])[0]
    if title!=character.get('title',0):
        raise ValueError('Current title input differs from emitted Unit')
    groups=numeric_groups(snapshot['resonance']);progress=progress_fields(snapshot['resonance'])
    account=snapshot['resonance']['account']
    level,xp,aux,enabled=struct.unpack('>iQiB',mapping['0x471'])
    if (level,xp,aux,bool(enabled))!=(account['level'],account['experience'],0,account['enabled']):
        raise ValueError('Resonance authority differs from emitted Unit')
    return dict(owner_uid=owner,source_sha256=snapshot['source_sha256'],base=base,title_id=title,
        full_copy=copied,named_options=(),resonance_level=level,
        resonance_points={sid:points for tab,rows in groups for sid,points in rows},
        resonance_override=progress[:2],numeric_options=groups,progress=progress)
