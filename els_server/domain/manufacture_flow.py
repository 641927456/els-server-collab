"""DX11 town manufacture route with current-state retry synchronization."""
import time,sqlite3,logging
from els_server.protocol.protocol_codec import Event
from els_server.protocol.manufacture_messages import manufacture_ack
from els_server.protocol.profession_messages import ProfessionState,level_update,selection_ack

def handle(session,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x198,0x4c2):return None
    from els_server.storage.manufacture import execute,select_alchemist
    from els_server.domain.manufacture_rules import policy
    if policy()['mode']!='compatibility-v1':return None
    valid=(session.item_test and session.client_build=='dx11_260923' and session.role=='game'
           and session.phase=='town_ready' and type(sequence) is int and 1<=sequence<2**32
           and session.account.store is not None and session.account.characters is not None)
    if event.kind==0x4c2:
        try:
            if not valid:raise ValueError('Profession selection state')
            wire=select_alchemist(session.account.store.path,session.account.uid,session.account.account_id,event.payload)
        except (ValueError,sqlite3.Error) as exc:
            if isinstance(exc,sqlite3.Error):logging.getLogger(__name__).exception('Profession transaction rejected')
            wire=selection_ack(-1,ProfessionState(),{},tail_u64=0,tail_i32=0,tail_flag_a=False,tail_flag_b=False)
        return [Event(0x201,kind=0x4c3,payload=wire)]
    try:
        if not valid:raise ValueError('Manufacture session state')
        operation=f'{session.shop_session_id}:{session.account.uid}:manufacture:{sequence}'
        receipt=execute(session.account.store.path,session.account.uid,session.account.account_id,event.payload,operation,now=int(time.time()))
    except (ValueError,sqlite3.Error) as exc:
        if isinstance(exc,sqlite3.Error):logging.getLogger(__name__).exception('Manufacture transaction rejected')
        ed=session.account.get_reward_balances()['ed'] if session.account.store else 0
        return [Event(0x201,kind=0x199,payload=manufacture_ack(result=-1,rewards={},changes=[],ed=ed,profession_xp=0,limit_id=0,limit_value=0))]
    answer=[Event(0x201,kind=0x199,payload=receipt['response'])]
    if receipt['leveled']:
        answer.append(Event(0x201,kind=0x4c4,payload=level_update(session.account.uid,receipt['state'],{})))
    if receipt['requires_inventory_sync']:answer.append(session.saved_user_sync())
    if receipt.get('inventory_refresh'):
        from els_server.storage.inventory_management import _updates
        answer.extend(_updates(receipt['inventory_refresh']))
    return answer
