"""Original 38100 modes and per-run ST_E_HENIR_QUICK_SLOT supplies."""
import struct,time
from els_server.protocol.protocol_codec import Event,encode_event

DUNGEON=38100
GRAPH='b77b20ece19a92eab13e6fcd03b2c9d61714c262b1a803505b104441d5053b6c'
ENTRY_MAGIC=b'HNR1'
# Same-build Enum.lua: DM_HENIR_PRACTICE1 / CHALLENGE2; temporary bag20.
SUPPLIES=((190826,10,44,1),(190827,10,45,1),(190828,3,46,30),(190898,3,46,30))


def entry(s,payload):
    """Signed producer forwards byte6 of the original eighteen-byte entry DTO."""
    if len(payload)<13 or payload[-13:-9]!=ENTRY_MAGIC:raise ValueError('Henir native selected mode missing')
    owner,mode=struct.unpack('>QB',payload[-9:])
    if owner!=s.account.uid or mode not in (1,2):raise ValueError('Henir selected mode owner/value')
    if mode==2 and DUNGEON not in s.account.character().get('cleared_dungeons',()):
        raise ValueError('Clear ordinary Henir before challenge')
    return payload[:-13],mode


def bind(run,mode):
    if mode not in (1,2) or run.graph['source_sha256']!=GRAPH:raise ValueError('Henir mode/source')
    run.henir_mode=mode
    # 36 is the legacy two-way selector, 37 its exit. Neither is a combat room.
    pool=[r['stage'] for r in run.encounter['pool'] if r['stage'] not in (0,36,37,44,45)]
    pool.sort(key=lambda stage:run.draw('henir-room:'+str(stage),2**128))
    count=20 if mode==1 else 6
    run.rotation=[0,*pool[:count-2],44 if mode==1 else 45]
    run.henir_supplies=[r[1] for r in SUPPLIES]
    run.henir_cooldowns={}
    run.henir_uses={}


def condition(run):
    return 1 if run.stage in (44,45) else next(r['condition'] for r in run.encounter['pool'] if r['stage']==run.stage)


def metadata(run,original):
    # B2 reader 2B4CEF0 +5D/+61 -> C2BCD0 -> 104EC90(current,total).
    return original[:-8]+struct.pack('>ii',run.round+1,len(run.rotation))


def _record(run,slot):
    """Use the common item body codec with a finite non-persistent template set.

    These four templates are deliberately not admitted into player inventory.
    The native temporary equipped tab is addressed by slot, not saved bindings.
    """
    from els_server.domain.inventory_items import _encode_item_body
    from els_server.domain.fashion_state import empty_record
    count=run.henir_supplies[slot]
    if count==0:return empty_record(20,slot)
    template=SUPPLIES[slot][0]
    # Native acknowledgement consumers test the instance ID as signed int64.
    item=dict(uid=0x7ffe000000000001+slot,template=template,metadata=2,group=20,slot=slot,count=count)
    return struct.pack('>QBh',item['uid'],20,slot)+_encode_item_body(item)+bytes(9)


def initialize(s):
    run=s.dungeon_run
    if run.identity!=DUNGEON:return []
    # C25B90/3F8 -> C36EE0 -> native inventory197DAD0, then305FF30 refresh.
    return [Event(0x201,kind=0x3f8,payload=struct.pack('>I',4)+b''.join(_record(run,n) for n in range(4))+struct.pack('>iQ',0,s.account.uid))]


def _ack(run,slot,*,result=0,template=-1,cooldown=-1.0):
    return Event(0x201,kind=0x114,payload=struct.pack('>i',result)+_record(run,slot)+struct.pack('>i?fH',template,False,cooldown,0))


def use(s,event,sequence):
    run=s.dungeon_run
    if run is None or run.identity!=DUNGEON or s.phase!='dungeon_active':return None
    from els_server.protocol.consumable_messages import request,effect,acknowledgement
    from els_server.domain.equipment_chip_flow import current_lease
    if (event.event_id!=0x202 or event.kind!=0x113 or event.performers not in ((),(0,))
        or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
        or s.role!='game' or s.phase!='dungeon_active' or not s.dungeon_substage_synced
        or s.clear_notified or getattr(s,'dungeon_failed',False) or not current_lease(s)
        or type(sequence)is not int or not 1<=sequence<2**32):
        return [acknowledgement(result=2005,automatic=event.kind==0x65e)]
    try:slot=request(event.payload)
    except ValueError:return [acknowledgement(result=500)]
    if slot>=len(SUPPLIES):return [acknowledgement(result=500)]
    previous=run.henir_uses.get(sequence)
    if previous is not None:
        return [_ack(run,slot,result=0 if previous==event.payload else 500)]
    now=time.monotonic();template,_,group,duration=SUPPLIES[slot]
    if now<run.henir_cooldowns.get(group,0):return [_ack(run,slot,result=1369)]
    if not run.henir_supplies[slot]:return [_ack(run,slot,result=500)]
    # Prepare/encode before changing the live run. No inventory or save writes.
    import copy
    pending=copy.copy(run);pending.henir_supplies=list(run.henir_supplies)
    pending.henir_supplies[slot]-=1
    replies=[_ack(pending,slot,template=template,cooldown=duration),effect(s.account.uid,template)]
    for reply in replies:encode_event(reply)
    if s.dungeon_run is not run or not current_lease(s):raise ValueError('Henir actor/run changed')
    run.henir_supplies=pending.henir_supplies
    run.henir_cooldowns[group]=now+duration
    run.henir_uses[sequence]=bytes(event.payload)
    return replies
