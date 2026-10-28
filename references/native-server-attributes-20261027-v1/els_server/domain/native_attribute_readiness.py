"""Current skill-UI readiness from the original owned6E9 business transition.

Native13A397F constructs the skill trees before7E9610 sends202/6E9.
Whole484 separately rejects absent Game558 or Game558+88. A socket write,
an old completed-request set or a same-UID reconnect does not attest readiness.
This captures server metadata inside the existing serialized business worker.
"""
from dataclasses import dataclass,field
import sys
from els_server.protocol.protocol_codec import Event
from els_server.domain.native_skill_production import _selection


@dataclass(frozen=True)
class SkillUIReceipt:
    epoch:object
    request:Event
    request_sequence:int
    reply:Event
    owner:int
    session:object=field(repr=False)
    account:object=field(repr=False)
    store:object=field(repr=False)
    token:str=field(repr=False)

    def current(self):
        value=_selection(self.session,self.epoch)
        return (value is not None and value[0]is self.account
            and value[1]is self.store and value[2]==self.token
            and value[3]in('skill_ui_ready','initialization_confirmed',
                'map_loading','square_accepted','town_ready',
                'dungeon_loading','dungeon_active'))


@dataclass(frozen=True)
class ProducedReadiness:
    messages:tuple
    receipt:object


def capture(epoch,session,produce,request,*,request_sequence=None):
    """Invoke the original bound handler once; evidence never changes replies.

    Duplicate6E9, other requests, changed selections and wrong current builds
    cannot create a fresh receipt. The receipt's original6EA Event must still
    be written before the delivery cursor may advance its readiness state.
    """
    from els_server.domain.native_attribute_delivery import ActorEpoch
    # The real application has already loaded its classes before its worker
    # runs. Metadata must not import account/resource initialization here.
    classes=tuple(value for module,name in(
        ('els_server.domain.local_session','LocalSession'),
        ('els_server.application','FriendsSession'))
        if isinstance(value:=getattr(sys.modules.get(module),name,None),type))
    before=_selection(session,epoch)if type(epoch)is ActorEpoch else None
    qualified=(type(session)in classes
        and getattr(produce,'__self__',None)is session
        and getattr(produce,'__func__',None)is type(session).handle
        and getattr(session,'client_build',None)=='dx11_260923'
        and getattr(session,'enter_town',False)is True
        and type(request)is Event and request.event_id==0x202
        and request.kind==0x6e9 and request.payload==b''
        and request.performers in((),(0,)) and request.payload_mode==0
        and request.uid==request.target_uid==2**64-1
        and type(request_sequence)is int and 1<=request_sequence<2**32
        and before is not None and before[3]=='player_initialized')
    messages=tuple(produce(request,request_sequence=request_sequence))
    if any(type(event)is not Event for event in messages):
        raise ValueError('Original synchronous readiness reply Events required')
    after=_selection(session,epoch)if type(epoch)is ActorEpoch else None
    replies=tuple(e for e in messages if e.event_id==0x201 and e.kind==0x6ea)
    same=(qualified and after is not None and after[3]=='skill_ui_ready'
        and before[0]is after[0]and before[1]is after[1]
        and before[2]==after[2]and len(replies)==1)
    receipt=(SkillUIReceipt(epoch,request,request_sequence,replies[0],epoch.owner_uid,
        session,after[0],after[1],after[2])if same else None)
    return ProducedReadiness(messages,receipt)
