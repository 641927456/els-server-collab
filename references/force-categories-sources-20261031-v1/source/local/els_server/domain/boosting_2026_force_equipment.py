"""Native passive-force slots and selected-book equip/unequip requests."""
import struct
from els_server.domain.boosting_2026_force_inventory import owned,ForceRuleError,catalog
from els_server.protocol.protocol_codec import Event
from els_server.domain.native_force_catalog import exclusion_group

PASSIVE_SLOTS=3
MOD_SLOTS=8
LEGACY_TYPE20_SLOT_LIMIT=5
TOTAL_SLOTS=PASSIVE_SLOTS+MOD_SLOTS

def master_skill(skill):return any(r['skill']==skill and r.get('required_master') for r in catalog().values())

def active_skill(skill):return any(r['skill']==skill and r.get('active') for r in catalog().values())
def change_skill(skill):return any(r['skill']==skill and r.get('change') for r in catalog().values())
# The client specifies one destination, but retail server swap behavior is not
# available. Keep this explicitly local: move the requested exclusion group to
# that destination; displaced skills remain owned. Do not call this retail swap.
LOCAL_RELOCATION_POLICY='requested-target-clears-prior-exclusion-group-v1'

def third_slot_unlocked(character):
    artifact=(character or {}).get('artifact')
    return bool((character or {}).get('master') and artifact and artifact['evolution']>=4)

def slots(character=None,*,visible=False):
    values=(character or {}).get('force_slots',((0,0),)*PASSIVE_SLOTS)
    if not isinstance(values,(tuple,list)) or len(values) not in (PASSIVE_SLOTS,TOTAL_SLOTS):raise ValueError('Native force slot count')
    values=tuple(values)+((0,0),)*(TOTAL_SLOTS-len(values))
    pairs={(r['skill'],r['rank']) for r in owned(character)};seen=set();result=[]
    for index,pair in enumerate(values):
        if not isinstance(pair,(tuple,list)) or len(pair)!=2 or any(type(v) is not int for v in pair):raise ValueError('Force slot identity')
        pair=tuple(pair)
        if pair!=(0,0):
            if pair not in pairs:raise ValueError('Unowned equipped force grade')
            if index<PASSIVE_SLOTS:
                if active_skill(pair[0]) or change_skill(pair[0]):raise ValueError('Native passive force category')
            elif not (change_skill(pair[0]) or active_skill(pair[0]) and index<PASSIVE_SLOTS+LEGACY_TYPE20_SLOT_LIMIT):
                raise ValueError('Native change slot or retained legacy type20 reference')
            # The three selected IDs have distinct original native base groups;
            # each ID's rare/unique ranks share that same exclusion group.
            group=exclusion_group(pair[0])
            if group in seen:raise ValueError('Duplicate native force exclusion group')
            seen.add(group)
        result.append(pair)
    if visible:
        from els_server.domain.character_rules import CLASSES
        if character is None or CLASSES[character['unit_class']]['stage']<3:return ((0,0),)*TOTAL_SLOTS
        if not character.get('master'):result=[(0,0) if skill and master_skill(skill) else (skill,rank) for skill,rank in result]
        if not third_slot_unlocked(character):result[2]=(0,0)
        # Historical type20 Mod rows remain persisted but invisible to the
        # native type18 vector. Genuine type18 rank1 rows remain visible.
        for index in range(PASSIVE_SLOTS,TOTAL_SLOTS):
            if result[index][0] and active_skill(result[index][0]):result[index]=(0,0)
    return tuple(result)

def vectors(character=None):
    layout=slots(character,visible=True);passive=layout[:PASSIVE_SLOTS];mods=layout[PASSIVE_SLOTS:]
    # DAF6E0: two DB5B10 vectors, six-byte (ID,rank,bool) records.
    # 8FA130 writes three passive entries at+1DD4 and eight Mod/change at+1DEC.
    return struct.pack('>I',PASSIVE_SLOTS)+b''.join(struct.pack('>iBB',s,r,0) for s,r in passive)+struct.pack('>I',MOD_SLOTS)+b''.join(struct.pack('>iBB',s,r,0) for s,r in mods)

def request(payload):
    # C560F0 emits exactly three i32 values and one byte for kind6D0.
    if not isinstance(payload,bytes) or len(payload)!=13:raise ValueError('Force equipment request size')
    kind,index,skill,rank=struct.unpack('>iiiB',payload)
    if kind not in (0,1,2) or skill<=0:raise ValueError('Force request category')
    if active_skill(skill) and kind:raise ValueError('Type20 uses ordinary122, not change6D0')
    if kind==1 and (change_skill(skill) or rank not in (3,4,5,6) or index not in range(PASSIVE_SLOTS)):
        raise ValueError('Native passive force request')
    if kind==2 and (not change_skill(skill) or rank!=1 or index not in range(MOD_SLOTS)):
        raise ValueError('Native type18 change force request')
    if kind==0 and (index!=0 or rank not in ((1,) if change_skill(skill) else (3,4,5,6))):
        raise ValueError('Native force removal request')
    return kind,index,skill,rank

def changed(character,payload):
    kind,index,skill,rank=request(payload)
    from els_server.domain.character_rules import CLASSES
    if CLASSES[character['unit_class']]['stage']<3 or character['level']<99:raise ForceRuleError(1903,'Third job force requirement')
    if (skill,rank) not in {(r['skill'],r['rank']) for r in owned(character)}:raise ValueError('Force equipment requires exact owned grade')
    if kind and master_skill(skill) and not character.get('master'):raise ValueError('Current native force requires Master class')
    if change_skill(skill):
        from els_server.domain.change_force_inventory import by_skill,for_character
        for_character(by_skill()[skill]['item'],character)
    result=list(slots(character))
    if kind==0:
        # Passive right-click uses type0/index0. Keep explicit historical
        # type20 cleanup compatibility; reads never erase old mistaken rows.
        return tuple((0,0) if pair==(skill,rank) else pair for pair in result)
    if kind==1 and index==2 and not third_slot_unlocked(character):raise ValueError('Third passive requires native Artifact evolution4')
    destination=index if kind==1 else PASSIVE_SLOTS+index
    result=[(0,0) if pair[0] and exclusion_group(pair[0])==exclusion_group(skill) else pair for pair in result]
    result[destination]=(skill,rank)
    return slots(dict(character,force_slots=result))

def acknowledgement(preset=b'',result=0,*,owner=None):
    if not preset:preset=bytes(16) # Four empty containers on a refusal.
    event=Event(0x201,kind=0x6d1,payload=struct.pack('>i',result)+preset)
    if owner is None:return event
    from els_server.domain.native_skill_production import record as record_native_skill
    return record_native_skill(event,owner)
