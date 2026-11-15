"""Native daily reward catalog and independent remaining-count map."""
import struct
from functools import lru_cache

from els_server.protocol.protocol_codec import Event


@lru_cache(maxsize=1)
def catalog_notification():
    from els_server.domain.ariel_daily_special_rules import data

    maps = data()['maps']
    payload = bytearray(struct.pack('>I', len(maps)))
    for dungeon, rule in sorted(maps.items(), key=lambda entry: int(entry[0])):
        by_unit = {0: rule['rewards']} if rule['rewards'] is not None else {
            int(unit): rewards for unit, rewards in rule['unit_rewards'].items()
        }
        units = sorted(by_unit)
        slots = tuple(zip(*(by_unit[unit] for unit in units), strict=True))
        payload.extend(struct.pack('>iI', int(dungeon), len(slots)))
        for slot in slots:
            quantity = slot[0][1]
            if any(count != quantity for _, count in slot):
                raise ValueError('Native daily reward slot must share quantity across units')
            # BE6970 loads these display slots into the map read by 804760.
            payload.extend(struct.pack('>iI', 0, len(units)))
            for unit, (template, _) in zip(units, slot, strict=True):
                payload.extend(struct.pack('>Bi', unit, template))
            payload.extend(struct.pack('>i?', quantity, False))
    # A51 also contains a scalar and a separate map. Ordinary daily catalog
    # uses only the first map. The other fields have native zero defaults.
    payload.extend(bytes(8))
    return Event(0x201, kind=0xa51, payload=bytes(payload))


def notification(rows,moment,*,mirror_remaining,temple_used):
    from els_server.domain.ariel_daily_special_rules import data as daily_catalog
    if type(mirror_remaining)is not int or not 0<=mirror_remaining<=5:raise ValueError('Mirror weekly count bounds')
    rules=daily_catalog()['maps']
    if type(moment)is not int or not 0<=moment<2**40 or type(rows)is not tuple or len(rows)!=len(rules):raise ValueError('Normal daily complete snapshot')
    if type(temple_used)is not int or not 0<=temple_used<=10:raise ValueError('Temple weekly count bounds')
    data=struct.pack('>I',len(rows)+2);previous=0
    for row in rows:
        if(type(row)is not tuple or len(row)!=3 or any(type(v)is not int for v in row)):raise ValueError('Normal daily row types')
        dungeon,used,maximum=row
        rule=rules.get(str(dungeon))
        if not previous<dungeon or rule is None or maximum!=rule['daily_count'] or not 0<=used<=maximum:raise ValueError('Normal daily count boundary')
        previous=dungeon
        # Native ctor defaults1/false/current time64/false/false; normal
        # builder admits discriminator0. FieldD is not a reset deadline.
        data+=struct.pack('>iI',dungeon,1)+struct.pack('>iii?qi??',1,used,maximum,False,moment,0,False,False)
    if any(r[0] in (35710,35860) for r in rows):raise ValueError('Weekly provider key collision')
    # Keep both providers: the native reader replaces this whole map. The
    # Mirror time field stays its verified opaque compatibility zero.
    # 2CC4B29 and 1979000 select Temple key 35710 and row category 1.
    data+=struct.pack('>iIiii?qi??',35710,1,1,temple_used,10,False,0,1,False,False)
    data+=struct.pack('>iIiii?qi??',35860,1,1,5-mirror_remaining,5,False,0,19,False,False)
    return Event(0x201,kind=0x861,payload=data)
