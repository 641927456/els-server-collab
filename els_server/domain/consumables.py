"""Verified native metadata. Broader effects remain catalog-only."""
import functools,hashlib,json,math,struct
from els_server.game_data import DATA_DIR,CLIENT_SHA


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(DATA_DIR/'consumables.json').read_bytes()
    m=json.loads((DATA_DIR/'consumables.manifest.json').read_text(encoding='utf8'))
    if m['schema_version']!=1 or m['client_sha256']!=CLIENT_SHA or hashlib.sha256(raw).hexdigest()!=m['sha256']:
        raise ValueError('Consumable catalog identity')
    rows=json.loads(raw)
    if len(rows)!=m['count'] or len({r['id'] for r in rows})!=len(rows):raise ValueError('Consumable cardinality')
    for r in rows:
        b=bytes.fromhex(r['record_hex'])
        if len(b)!=232 or struct.unpack_from('<I',b)[0]!=r['id'] or b[0xd6]!=r['cooldown_seconds']:
            raise ValueError('Consumable record identity')
        if any(len(bytes.fromhex(h))!=24 for h in r['effects']):raise ValueError('Consumable effect width')
    return {r['id']:r for r in rows}


def ordinary(template):
    if template in (710313,710314,710315):
        from els_server.domain.apple_consumables import usable
        return usable(template)
    # Enable only individually checked HP/MP potions. Other rows may
    # require buff, quest, event, targeting or reward behavior not yet wired.
    # minimum level, shared cooldown group, seconds, ordered native effects.
    # 1AB9D20 iterates the full vector: kind 13 is proportional HP recovery,
    # kind 2 restores MP. Send one 115, never one notification per effect.
    expected={77000:(0,1,30,((1,3500),)),77010:(0,4,30,((2,50),)),
              77170:(0,1,30,((1,6200),)),77180:(0,4,30,((2,100),)),
              77190:(0,1,30,((1,9200),)),77270:(0,1,30,((1,15200),)),
              77420:(0,3,30,((13,15),(2,100))),
              77430:(0,3,30,((13,30),(2,100))),
              78902:(0,48,60,((2,150),)),78930:(60,4,30,((2,225),))}
    if template not in expected:raise ValueError('Consumable effect not implemented')
    level,group,seconds,effects=expected[template];r=catalog()[template]
    raw=bytes.fromhex(r['record_hex'])
    # Every enabled row already has independent native inventory body proof.
    # Pin the level field, too; the transaction checks the current character.
    # Linked buffs and additional effects remain outside the supported set.
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    if VERIFIED_TEMPLATES.get(template)!=2 or TEMPLATE_BAG_GROUPS.get(template)!=6 or raw[0xd1]!=level or struct.unpack_from('<I',raw,0xa8)[0]:
        raise ValueError('Ordinary potion condition not supported')
    if r['effects']!=[struct.pack('<6I',kind,0,amount,0,0,0).hex() for kind,amount in effects] or (r['cooldown_group'],r['cooldown_seconds'])!=(group,seconds):
        raise ValueError('Ordinary potion evidence changed')
    return r


def require_usable(template,level,*,automatic=False):
    if automatic and template in (710313,710314,710315):raise ValueError('Apple pet automation is not admitted')
    metadata=ordinary(template)
    if type(level) is not int or not 1<=level<=99:raise ValueError('Consumable character level')
    if level<bytes.fromhex(metadata['record_hex'])[0xd1]:raise ValueError('Consumable level requirement')
    return metadata


def recovery_cooldown_seconds(base_seconds,reduction):
    """Original3056073/305F496 arithmetic for the admitted pet modifier.

    Each SSE multiply/add rounds to FLOAT32. The captured bias is0.05,
    not0.5. Keep the existing server modifier admission at0..0.9.
    This does not activate engraving or other unimplemented BUFF effects.
    """
    if type(base_seconds) is not int or not 0<=base_seconds<=255:
        raise ValueError('Consumable native base cooldown')
    if type(reduction) not in (int,float) or not math.isfinite(reduction) or not 0<=reduction<=.9:
        raise ValueError('Consumable admitted cooldown reduction')
    def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]
    return base_seconds-int(f32(f32(base_seconds*f32(reduction))+f32(.05)))
