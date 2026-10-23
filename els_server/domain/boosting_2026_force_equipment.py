"""Native passive-force slots and selected-book equip/unequip requests."""
import struct
from els_server.domain.boosting_2026_force_inventory import owned,ForceRuleError
from els_server.protocol.protocol_codec import Event

PASSIVE_SLOTS=3
ACTIVE_SLOTS=8
# The client specifies one destination, but retail server swap behavior is not
# available. Keep this explicitly local: move the requested exclusion group to
# that destination; displaced skills remain owned. Do not call this retail swap.
LOCAL_RELOCATION_POLICY='requested-target-clears-prior-exclusion-group-v1'

def third_slot_unlocked(character):
    artifact=(character or {}).get('artifact')
    return bool((character or {}).get('master') and artifact and artifact['evolution']>=4)

def slots(character=None,*,visible=False):
    values=(character or {}).get('force_slots',((0,0),)*PASSIVE_SLOTS)
    if not isinstance(values,(tuple,list)) or len(values)!=PASSIVE_SLOTS:raise ValueError('Native passive force slot count')
    pairs={(r['skill'],r['rank']) for r in owned(character)};seen=set();result=[]
    for pair in values:
        if not isinstance(pair,(tuple,list)) or len(pair)!=2 or any(type(v) is not int for v in pair):raise ValueError('Force slot identity')
        pair=tuple(pair)
        if pair!=(0,0):
            if pair not in pairs:raise ValueError('Unowned equipped force grade')
            # The three selected IDs have distinct original native base groups;
            # each ID's rare/unique ranks share that same exclusion group.
            if pair[0] in seen:raise ValueError('Duplicate native force exclusion group')
            seen.add(pair[0])
        result.append(pair)
    if visible:
        from els_server.domain.character_rules import CLASSES
        if character is None or CLASSES[character['unit_class']]['stage']<3:return ((0,0),)*PASSIVE_SLOTS
        if not third_slot_unlocked(character):result[2]=(0,0)
    return tuple(result)

def vectors(character=None):
    passive=slots(character,visible=True)
    # DAF6E0: two DB5B10 vectors, six-byte (ID,rank,bool) records.
    # 8FA130 writes three passive entries at+1DD4 and eight active at+1DEC.
    return struct.pack('>I',PASSIVE_SLOTS)+b''.join(struct.pack('>iBB',s,r,0) for s,r in passive)+struct.pack('>I',ACTIVE_SLOTS)+bytes(ACTIVE_SLOTS*6)

def request(payload):
    # C560F0 emits exactly three i32 values and one byte for kind6D0.
    if not isinstance(payload,bytes) or len(payload)!=13:raise ValueError('Force equipment request size')
    kind,index,skill,rank=struct.unpack('>iiiB',payload)
    if kind not in (0,1) or skill<=0 or rank not in (3,4,5):raise ValueError('Selected passive force request')
    if (kind==0 and index!=0) or (kind==1 and index not in range(PASSIVE_SLOTS)):raise ValueError('Force slot index')
    return kind,index,skill,rank

def changed(character,payload):
    kind,index,skill,rank=request(payload)
    from els_server.domain.character_rules import CLASSES
    if CLASSES[character['unit_class']]['stage']<3 or character['level']<99:raise ForceRuleError(1903,'Third job force requirement')
    if (skill,rank) not in {(r['skill'],r['rank']) for r in owned(character)}:raise ValueError('Force equipment requires exact owned grade')
    result=list(slots(character))
    if kind==0:
        # Original right-click on an activated force sends type0/index0,
        # identifying the force by ID+rank rather than a destination index.
        return tuple((0,0) if pair==(skill,rank) else pair for pair in result)
    if index==2 and not third_slot_unlocked(character):raise ValueError('Third passive requires native Artifact evolution4')
    result=[(0,0) if pair[0]==skill else pair for pair in result]
    result[index]=(skill,rank)
    return slots(dict(character,force_slots=result))

def acknowledgement(preset=b'',result=0):
    if not preset:preset=bytes(16) # Four empty containers on a refusal.
    return Event(0x201,kind=0x6d1,payload=struct.pack('>i',result)+preset)
