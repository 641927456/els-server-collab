"""Original pet gesture request/ack/notification; no learned-skill grants."""
import hashlib,struct
from els_server.protocol.companion_messages import event
from els_server.storage.companion_state import snapshot

# 2DB7E20's explicit cases. Attack and cheer run through native battle AI;
# they must not be invented as gesture IDs or enabled by this route.
GESTURES=frozenset((1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25))

def handle(session,request,sequence):
    if request.kind!=0x2ef or request.event_id!=0x202 or session.client_build!='dx11_260923' or not session.item_test:return None
    def ack(result):return event(0x2f0,struct.pack('>i',result))
    if (session.role!='game' or session.phase not in ('town_ready','dungeon_active')
            or type(sequence) is not int or not 1<=sequence<2**32 or len(request.payload)!=5):return [ack(-1)]
    # 2DBF9A0 -> 2E11460: gesture, variation, flag, two talk-box choices.
    gesture,variation,flag,_,_=struct.unpack('>5B',request.payload)
    # Native self-pet state transition at 2D85764..2D85773 explicitly sends
    # gesture13 with both optional bytes255; 2DB7E47 stores the third byte
    # unchanged. Keep this proven sentinel tuple, not arbitrary flag values.
    native_idle_sentinel=(gesture,variation,flag)==(13,255,255)
    if gesture not in GESTURES or variation not in (0,1,255) or (flag>1 and not native_idle_sentinel):return [ack(-1)]
    saved=snapshot(session.account.store.path,session.account.uid)
    if not saved['pet'] or not any(p['kind']=='pet' and p['uid']==saved['pet'] for p in saved['companions']):return [ack(-1)]
    digest=hashlib.sha256(request.payload).digest()
    receipts=getattr(session,'pet_action_receipts',None)
    if receipts is None:receipts=session.pet_action_receipts={}
    if sequence in receipts:return [ack(0 if receipts[sequence]==digest else -1)]
    receipts[sequence]=digest
    if len(receipts)>256:receipts.pop(next(iter(receipts)))
    # 2DADE20 reads owner UID and three bytes, then 2DB7E20 selects the
    # registered state of that owner's already-spawned pet.
    return [ack(0),event(0x2f1,struct.pack('>QBBB',session.account.uid,gesture,variation,flag))]
