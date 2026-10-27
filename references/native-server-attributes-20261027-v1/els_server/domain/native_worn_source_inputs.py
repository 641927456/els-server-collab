"""Canonical owned item sources for original worn and set collectors.

Resource and owner contexts are supplied explicitly after the SQL snapshot is
released. Secondary equipment is Master Artifact gear (group24); ordinary
costumes remain in group9. The main DTO also includes fishing equipment.
"""
from functools import lru_cache
import hashlib,json,struct
from els_server.domain.native_dynamic_sets import derive_set_id,property_value
from els_server.domain.native_item_option_vectors import project
from els_server.domain.native_option_colors import colors
from els_server.domain.native_set_sources import item_pools


@lru_cache(maxsize=1)
def canonical_defaults():
    from els_server.domain.inventory_items import fixture
    value=fixture();raw=bytes.fromhex(value['wire_hex'])
    # This is the actual ordinary writer seed, not guessed instance defaults.
    encoded=(json.dumps(value,sort_keys=True,separators=(',',':'))).encode()
    fields={int(row['offset'],0):row['wire_offset']for row in value['fields']}
    if raw[fields[0x33d]:fields[0x33d]+4]!=bytes(4):
        raise ValueError('Canonical legacy item mutation map is no longer empty')
    return (struct.unpack_from('>h',raw,fields[9])[0],
            struct.unpack_from('>b',raw,fields[12])[0],
            hashlib.sha256(encoded).hexdigest())


def equipment_vectors(items):
    """Same ordered DTO12E/13E entries as the installed canonical writers."""
    if type(items)is not tuple:raise ValueError('Owned immutable item vector required')
    if len({row['uid']for row in items})!=len(items):raise ValueError('Duplicate owned item UID')
    from els_server.domain.fishing_equipment import equipment_entries
    main=[(row['slot'],row)for row in items if row['group']==9]+equipment_entries(items)
    secondary=[(row['slot'],row)for row in items if row['group']==24]
    for rows in(main,secondary):
        if len({key for key,row in rows})!=len(rows):raise ValueError('Duplicate native equipment key')
    return tuple(row['uid']for key,row in sorted(main)),tuple(row['uid']for key,row in sorted(secondary))


def bind(item,record,option_source,*,owner_status,at):
    from els_server.domain.inventory_items import validate_item
    from els_server.domain.item_expiration import require_current
    if type(at)is not int or not 0<at<2**31-7200:
        raise ValueError('Explicit sampled native item validity time required')
    item=validate_item(item);require_current(item,now=at)
    if (type(record)is not bytes or len(record)!=232
            or struct.unpack_from('<I',record)[0]!=item['template']):
        raise ValueError('Owned current template record differs')
    if (type(owner_status)is not tuple or len(owner_status)!=2
            or any(type(v)is not bool for v in owner_status)):
        raise ValueError('Explicit native inventory owner/status context required')
    groups=tuple(tuple(item.get('option_groups',{}).get(str(n),()))for n in range(33))
    types={identity:option_source[identity][0]for identity in groups[1]if identity in option_source}
    vectors=project(groups,types,mutations=())
    properties,template_options=item_pools(record)
    circuit_colors=()
    if any(prop[0]==0x50 for prop in properties):
        from els_server.domain.equipment_circuit_rules import active_slots
        selected=active_slots(item['template'],vectors[0x2d8])
        circuit_colors=colors(tuple(vectors[0x2d8][p]for p in selected),4,option_source)
    four=tuple(colors(vectors[offset],1,option_source)for offset in(0xe8,0x100,0x118,0x130))
    spirit=colors(vectors[0x1c8],2,option_source)
    tenebrous=colors(vectors[0x218],3,option_source)
    durability,enhancement,seed_sha=canonical_defaults()
    flags4,flags8=struct.unpack_from('<2I',record,4)
    result=dict(uid=item['uid'],template_id=item['template'],native8=item['template'],
        nativeC=item['metadata'],native10=item.get('durability',durability),
        native14=item['count'],native18=item.get('enhancement',enhancement),
        flags4=flags4,flags8=flags8,required_class=record[0xd3],
        native318_present=owner_status[0],native318_7BD=owner_status[1],
        template_option40=property_value(properties,0x28),lookup_type=item['group'],
        slot_code=item['slot'],template_present=True,properties=properties,
        template_options=template_options,option_vectors=vectors,
        four_groups=four,color43=spirit,color3c=tenebrous,circuit_colors=circuit_colors,
        source_seed_sha256=seed_sha,
        valid_before=item['expires_at']+1 if 'expires_at'in item else None)
    result['resolved_set_id']=derive_set_id(struct.unpack_from('<I',record,0x24)[0],
        properties,four_groups=four,color43=spirit,color3c=tenebrous,circuit_colors=circuit_colors)
    return result
