"""Verified native metadata. Broader effects remain catalog-only."""
import functools,hashlib,json,math,struct
from els_server.game_data import DATA_DIR,CLIENT_SHA
from els_server.domain.festival_food import TEMPLATES as FESTIVAL_FOOD


class ConsumableCoolingDown(ValueError):
    """A qualified owned use is waiting for its original cooldown."""

    def __init__(self,message,*,slot):
        super().__init__(message)
        self.slot=slot


# Current shop/quest recovery inputs. No new acquisition source.
CURRENT_RECOVERY=frozenset((77060, 77080, 77090, 77130, 78140, 78170, 78240, 78270, 78995, 78996, 78998, 78999, 79000, 92290, 277155, 710012))
CURRENT_THROWABLES=frozenset((78340,78350))
CURRENT_MANUAL=CURRENT_RECOVERY|CURRENT_THROWABLES|FESTIVAL_FOOD|{710006,710250,185080}


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


def manual_recovery_definitions():
    """Source-qualified ordinary MP recoveries share the native bag6 body."""
    pins={710022:'0b87d5694633253a884210711329cc05a7932f0fdf4184f65d3793410c67203a',
          710012:'9cb21a2ea104d962bd41f27b81de1a52947c49cc9d26a9e3cd5c59face44c656'}
    result=[]
    for template,digest in pins.items():
        raw=bytes.fromhex(catalog()[template]['record_hex'])
        if (hashlib.sha256(raw).hexdigest()!=digest
            or(raw[7]&15,struct.unpack_from('<I',raw,0x10)[0])!=(2,500)):
            raise ValueError('Manual recovery inventory source changed')
        # Original19803A0 classification6 and the common owned-stack policy.
        result.append(dict(template=template,metadata=2,group=6,max_stack=500))
    return result


def ordinary(template):
    if template in FESTIVAL_FOOD:
        # The original effect notification invokes the complete native food vector.
        return catalog()[template]
    if template==185080:
        r=catalog()[template];raw=bytes.fromhex(r['record_hex'])
        if (hashlib.sha256(raw).hexdigest()!='fa7a71b6f427cdbeae0b0295a53b76c2a9bb678da5c061af438526ee7f07935a'
            or r['effects']!=[struct.pack('<6I',39,0,20,0,0,0).hex()]
            or (r['cooldown_group'],r['cooldown_seconds'])!=(22,30)):
            raise ValueError('Current mount fuel source')
        return r
    if template in (710006,710250):
        from els_server.domain.abyss_weapon_2026 import templates
        r=catalog()[template]
        expected=[struct.pack('<6I',13,0,100,0,0,0).hex(),struct.pack('<6I',19,0,100,0,0,0).hex()]
        if (hashlib.sha256(bytes.fromhex(r['record_hex'])).hexdigest()!=templates()[template]['record_sha256']
            or r['effects']!=expected or(r['cooldown_group'],r['cooldown_seconds'])!=((16 if template==710006 else 18),30)):
            raise ValueError('Campaign recovery native effects changed')
        return r
    from els_server.domain.consumable_extensions import quick_templates,ordinary as extended
    if template in quick_templates():return extended(template)
    if template in (130467,710193,723674,190624):
        # Exact existing owned Fighting Spirit records. Native115 consumes
        # A8 factors204/3517 -> non-world/non-stored212/3344, including timers.
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
    if template in CURRENT_THROWABLES:
        # Original1AB9D20 case18: arm wooden/light temporary weapon1/2.
        # Actor+35D4/+35D8 and native state0x46 remain client-owned.
        # One unchanged115 selects the complete native item effect vector.
        r=catalog()[template];raw=bytes.fromhex(r['record_hex'])
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        weapon={78340:1,78350:2}[template]
        if (VERIFIED_TEMPLATES.get(template),TEMPLATE_BAG_GROUPS.get(template),raw[0xd1],
            struct.unpack_from('<I',raw,0xa8)[0],r['cooldown_group'],r['cooldown_seconds'])!=(2,6,0,0,6,30):
            raise ValueError('Native temporary-weapon source changed')
        if r['effects']!=[struct.pack('<6I',18,0,weapon,1,0,0).hex()]:
            raise ValueError('Native temporary-weapon vector changed')
        return r
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
    expected[710022]=(0,19,30,((19,100),))
    expected[710012]=(0,52,30,((19,100),))
    expected.update({79063:(0,2,30,((13,50),)),79064:(0,5,30,((19,50),))})
    expected[79065]=(0,10,30,((19,50),(13,50)))
    expected[77110]=(0,14,30,((3,0),(5,0),(6,0)))
    expected.update({77060:(0,14,30,((6,0),)),77080:(0,14,30,((1,4500),(5,0))),
                     77090:(0,14,30,((2,50),(3,0))),77130:(0,5,30,((2,100),)),
                     78140:(0,2,30,((1,95600),(2,30))),78170:(0,2,30,((1,150000),(2,30))),
                     78240:(0,5,30,((1,28600),(2,150))),78270:(0,5,30,((1,45000),(2,190))),
                     78995:(0,1,30,((1,94300),)),78996:(0,1,30,((1,132300),)),
                     78998:(0,4,30,((2,75),)),78999:(0,4,30,((2,125),)),
                     79000:(0,4,30,((2,175),)),92290:(0,2,30,((1,109100),(2,30),(3,0)))})
    # Finite guide rewards: exact ordered KIM AC effects and native cooldowns.
    expected.update({710250:(0,18,30,((13,100),(19,100))),710006:(0,16,30,((13,100),(19,100))),
                     713170:(0,25,30,((13,75),(19,75))),710031:(0,11,30,((13,75),(19,75))),
                     710035:(0,10,30,((19,50),(13,50))),710010:(0,13,30,((13,30),(2,100),(3,0),(5,0),(6,0)))})
    # Current wedding cake: original ordered HP/MP effects and shared10s group.
    expected[277155]=(0,20,10,((13,100),(19,100)))
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
    from els_server.domain.consumable_extensions import quick_templates
    if automatic and template in (quick_templates()|CURRENT_MANUAL):raise ValueError('Extended consumables require manual use')
    if automatic and template in (710313,710314,710315,79065,77110,710022,130467,710193,723674,190624,710010):raise ValueError('Apple pet automation is not admitted')
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
