"""Original8C0/1/3/5 lifecycle on the current selected town actor."""
import time
from els_server.protocol import pet_expedition_messages as wire
from els_server.storage import pet_expedition as state


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0x8c1,0x8c3,0x8c5):return None
    from els_server.domain.tenebros_capacity_flow import selected
    try:
        path,owner,account,guard=selected(s)
        if (type(sequence)is not int or not 1<=sequence<2**32 or event.performers!=(0,)
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
            raise ValueError('Expedition native request envelope')
        return state.perform(path,owner,account,event.kind,event.payload,
            s.shop_session_id+':pet-expedition:'+str(owner)+':'+str(sequence),guard)
    except ValueError:
        from els_server.domain.quest_flow import account_source_actor
        if not account_source_actor(s):return []
        try:region,mission,_=wire.request(event.kind,event.payload)
        except ValueError:region,mission=1,1
        empty=dict(mission=mission,region=region,pets=[],started_at=0,ends_at=0)
        if event.kind==0x8c3:return [wire.completion_ack(result=2005,state=empty,rewards={},changes=[])]
        return [wire.state_ack(0x8c2 if event.kind==0x8c1 else 0x8c6,
            result=2005,native_auxiliary=0,ed=s.account.get_reward_balances()['ed'],state=empty)]


def initialize_login(s,answer):
    if not(s.item_test and s.client_build=='dx11_260923'and s.role=='game'
           and s.account.characters is not None and s.account.character()['level']==99):return answer
    from els_server.domain.fishing_attempt import _selection_binding,_same
    bound=_selection_binding(s)
    def guard(db):
        if not _same(s,bound):raise ValueError('Expedition original selected actor changed')
    events=state.initialize(s.account.store.path,s.account.uid,s.account.account_id,guard)
    from els_server.storage.life_stamina import day
    s.pet_expedition_day=day(time.time())
    return answer+events


def periodic(s):
    from els_server.storage.life_stamina import day
    now=time.time();previous=getattr(s,'pet_expedition_day',None)
    if previous==day(now):return []
    if not(s.item_test and s.client_build=='dx11_260923' and s.role=='game' and s.account.characters is not None):return []
    if s.account.character()['level']!=99:return []
    from els_server.domain.tenebros_capacity_flow import selected
    try:path,owner,account,guard=selected(s)
    except ValueError:return []
    events=state.initialize(path,owner,account,guard,now=int(now))
    s.pet_expedition_day=day(now)
    return events
