"""Route native pet support requests before generic item-use families."""
import sqlite3,struct,uuid
from contextlib import closing
from els_server.protocol import pet_support_messages as wire
from els_server.protocol.career_messages import use_ack
from els_server.storage import pet_support as state

KINDS={0x219,0x661,0x2fb,0x8c7,0x8a1}
def handle(session,event,sequence):
    if event.event_id!=0x202 or event.kind not in KINDS or session.client_build!='dx11_260923' or not session.item_test:return None
    if event.kind==0x8a1 and (len(event.payload)<4 or event.payload[:4]!=b'\0\0\0\2'):return None
    kind=event.kind;path=session.account.store.path;owner=session.account.uid
    setattr(session,'_pet_support_rejection',None)
    def detail(reason):
        # Bounded fields only: which item/pet the client named, never the body.
        if kind!=0x219:return dict(kind=kind,reason=reason)
        if len(event.payload)!=29:return dict(kind=kind,reason=reason,length=len(event.payload))
        item,pet,a,b,n,flag=struct.unpack('>QQiiIB',event.payload)
        return dict(kind=kind,reason=reason,item=item,pet=pet,a=a,b=b,n=n,flag=flag)
    def refusal(reason):
        setattr(session,'_pet_support_rejection',detail(reason))
        if kind==0x219:
            # The dialog is a state machine: it only leaves its pending state on
            # the settings update that follows a ticket use, so a bare negative
            # ack left it hanging. Echo the unchanged server state instead.
            with closing(sqlite3.connect(path)) as db:
                try:current=state.automatic(db,owner)
                except sqlite3.Error:return [use_ack(result=-1)]
            return [use_ack(result=-1),wire.settings(current,0xb3b)]
        if kind==0x8c7:return [wire.equipment_ack(result=-1)]
        if kind==0x8a1:return [state.bindings_initialization(path,owner,-1)]
        if kind==0x661:return [state.initialization(path,owner)]
        return [wire.pet_update(result=-1)]
    if session.role!='game' or session.phase not in (('town_ready',) if kind in (0x219,0x8c7) else ('town_ready','dungeon_active')):
        # Generic career/skill handlers retain their own invalid-phase reply.
        return None if kind==0x219 else refusal('phase')
    operation=session.shop_session_id+':pet:'+str(sequence if sequence is not None else uuid.uuid4())
    try:answer=state.handle(path,owner,kind,event.payload,operation)
    except (ValueError,UnicodeError) as error:return refusal(str(error))
    # A storage error that escapes unanswered leaves the pending dialog with no
    # transition at all, which is worse than a refusal the client can render.
    except sqlite3.Error:return refusal('storage unavailable')
    if answer is None and kind==0x219:
        # Not one of the pet products: the generic item families answer instead.
        setattr(session,'_pet_support_rejection',detail('unhandled item'))
    return answer
