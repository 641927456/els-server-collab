"""Verified native metadata. Broader effects remain catalog-only."""
import functools,hashlib,json,math,struct
from els_server.game_data import DATA_DIR,CLIENT_SHA


class ConsumableCoolingDown(ValueError):
    """Recovery-group refusal that also reports how long the caller still waits."""
    def __init__(self,remaining,slot=0):
        super().__init__('Consumable is cooling down')
        self.remaining=float(max(0.0,remaining))
        self.slot=slot


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


def _native_vector(effect):
    """Pad one native six-word effect vector.

    Ordinary rows are written as (kind, amount) and expand to the native
    (kind, 0, amount, 0, 0, 0). Element crystal balls need the third and fourth
    words as well, so they are written as the full prefix (18, 0, element, 1).
    """
    if len(effect)>6:raise ValueError('Consumable effect width')
    if len(effect)<3:return (effect[0],0,effect[1],0,0,0)
    return tuple(effect)+(0,)*(6-len(effect))


def manual_magic_potion_definition():
    """One source-qualified manual potion; this does not open an EP offer."""
    raw=bytes.fromhex(catalog()[710022]['record_hex'])
    if hashlib.sha256(raw).hexdigest()!='0b87d5694633253a884210711329cc05a7932f0fdf4184f65d3793410c67203a':
        raise ValueError('Manual magic potion source changed')
    if (raw[7]&15,struct.unpack_from('<I',raw,0x10)[0])!=(2,500):
        raise ValueError('Manual magic potion inventory source')
    # Original19803A0 classification:6. Source stack500 participates in the
    # existing owner-authorized999 minimum for ordinary stackable items.
    return dict(template=710022,metadata=2,group=6,max_stack=500)


# Local shortcut policy only: the catalog stays the immutable client mirror
# (record byte0xD6 keeps30), while the server-authoritative timer uses this
# value for the admitted row. 1AB9D20 reads its seconds from the same field.
LOCAL_COOLDOWN_SECONDS={130165:1}


def acknowledged_cooldown(template,seconds):
    """0x114 cooldown float; -1 keeps the native record value for other rows."""
    return float(LOCAL_COOLDOWN_SECONDS[template]) if template in LOCAL_COOLDOWN_SECONDS else -1.0


def ordinary(template):
    if template in (130467,710193,723674,190624):
        # Exact existing owned Fighting Spirit records. Native115 consumes
        # A8 factors204/3517 -> non-world/non-stored212/3344, including timers.
        # 190624 is the shop copy of the admitted 710193: same group12 timer
        # family, same empty effect vector, same level byte, only the A8
        # pointer differs because each record resolves its own BuffFactor.
        r=catalog()[template];raw=bytes.fromhex(r['record_hex'])
        pins={130467:'7299fb414a12255226ec2b402c7b863862ae37415be984688e2c6b72f3d94a65',
              710193:'6c2a3c49394f5f383f76774e54cd2a6df51676f66c79ec0df97b67167ebeefbe',
              723674:'5ca413679223b57d6a9af1127408a7ed3eb79f0ec2ea4859bc805c7f0ecbbb06',
              190624:'e12468c99330df6f173fdf3a725905e58cbe28cb02da469036e33a0af0f2b5b1'}
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        if (hashlib.sha256(raw).hexdigest()!=pins[template]
            or VERIFIED_TEMPLATES.get(template)!=2 or TEMPLATE_BAG_GROUPS.get(template)!=6
            or (r['cooldown_group'],r['cooldown_seconds'],r['effects'],raw[0xd1])!=(12,30,[],0)):
            raise ValueError('Fighting Spirit original source changed')
        return r
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
    # Two original epic reward potions; reuse native HP/MP effects and cooldown.
    expected.update({78985:(0,2,30,((1,190000),)),78986:(0,5,30,((2,150),))})
    expected[710000]=(0,15,30,((13,100),(19,100)))
    # Same verified full-recovery record as710000: HP kind13 100%, MP kind19
    # 100%, shared group15. Shortcut binding412 owns both, so the two rows must
    # stay byte-identical apart from the template id.
    expected[130165]=(0,15,30,((13,100),(19,100)))
    # Ancient fossil pill: identical native full-recovery vector (HP kind13
    # 100%, MP kind19 100%) with its own group 18, so it never shares the
    # binding-412 family timer. Only this template carries the verified
    # inventory body (VT=2, bag group 6); the cash-shop and Ariel copies do not.
    expected[135402]=(0,18,30,((13,100),(19,100)))
    expected[710022]=(0,19,30,((19,100),))
    expected.update({79063:(0,2,30,((13,50),)),79064:(0,5,30,((19,50),))})
    expected[79065]=(0,10,30,((19,50),(13,50)))
    expected[77110]=(0,14,30,((3,0),(5,0),(6,0)))
    # Four existing Ariel recovery rows. Effect vectors, cooldown groups and
    # level bytes are read verbatim from the catalog record; all three are
    # already implemented kinds (13=HP%, 19=MP%), and none of them carries a
    # linked-buff factor (record0xA8 == 0), so no buff behaviour is implied.
    # Each keeps its own group so it never shares another row's timer family.
    expected.update({710006:(0,16,30,((13,100),(19,100))),
                     710250:(0,18,30,((13,100),(19,100))),
                     710031:(0,11,30,((13,75),(19,75))),
                     713170:(0,25,30,((13,75),(19,75)))})
    # Two plain recovery rows already registered for inventory: 杨桃茶 restores
    # flat HP kind1 plus MP kind2, MP上级恢复药 restores MP kind2 only.
    expected.update({78982:(0,5,30,((1,55100),(2,200))),
                     79000:(0,4,30,((2,175),))})
    # Eight element crystal balls already owned. Native vector (18, 0, element,
    # level): kind18 carries the weapon-attribute index in the third word
    # (3 fire, 4 water, 5 earth, 6 wind, 7 light, 8 dark) and the granted
    # attribute level in the fourth (always 1). The index mapping is cross
    # checked by the two Ariel copies, which duplicate plain rows verbatim:
    # 712040 -> 4 equals 78370, 712041 -> 6 equals 78390. Every row keeps the
    # native group6 timer and no linked buff (record0xA8 == 0), so only the
    # client-side element application is implied; the server never interprets
    # kind18 and only charges the stack with one native 0x115 notice.
    expected.update({78360:(0,6,30,((18,0,3,1),)),78370:(0,6,30,((18,0,4,1),)),
                     78380:(0,6,30,((18,0,5,1),)),78390:(0,6,30,((18,0,6,1),)),
                     78400:(0,6,30,((18,0,7,1),)),78410:(0,6,30,((18,0,8,1),)),
                     712040:(0,6,30,((18,0,4,1),)),712041:(0,6,30,((18,0,6,1),))})
    if template not in expected:raise ValueError('Consumable effect not implemented')
    level,group,seconds,effects=expected[template];r=catalog()[template]
    raw=bytes.fromhex(r['record_hex'])
    # Every enabled row already has independent native inventory body proof.
    # Pin the level field, too; the transaction checks the current character.
    # Linked buffs and additional effects remain outside the supported set.
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    if VERIFIED_TEMPLATES.get(template)!=2 or TEMPLATE_BAG_GROUPS.get(template)!=6 or raw[0xd1]!=level or struct.unpack_from('<I',raw,0xa8)[0]:
        raise ValueError('Ordinary potion condition not supported')
    if r['effects']!=[struct.pack('<6I',*_native_vector(effect)).hex() for effect in effects] or (r['cooldown_group'],r['cooldown_seconds'])!=(group,seconds):
        raise ValueError('Ordinary potion evidence changed')
    if template in LOCAL_COOLDOWN_SECONDS:return dict(r,cooldown_seconds=LOCAL_COOLDOWN_SECONDS[template])
    return r


def require_usable(template,level,*,automatic=False):
    if automatic and template in (710313,710314,710315,79065,77110,710022,130467,710193,723674,190624):raise ValueError('Apple pet automation is not admitted')
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
