"""Town manufacture with current actor and precommit native reply checks."""
import time,sqlite3,logging
from pathlib import Path
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.manufacture_messages import manufacture_ack
from els_server.protocol.profession_messages import ProfessionState,level_update,selection_ack
from els_server.domain.equipment_chip_flow import current_lease

def _saved_paths(account):
    path=Path(account.store.path).resolve()
    return all(Path(facade.path).resolve()==path and getattr(facade,'uid',account.uid)==account.uid
        and getattr(facade,'account_id',account.account_id)==account.account_id
        for facade in (account.characters,getattr(account,'reward_store',None),getattr(account,'inventory_store',None))
        if facade is not None)

def _actor(session):
    account=getattr(session,'account',None);app=getattr(session,'application',None)
    return bool(account is not None and session.item_test and session.client_build=='dx11_260923'
        and session.role=='game' and session.phase=='town_ready'
        and account.store is not None and account.characters is not None
        and account.store.uid==account.uid and _saved_paths(account) and current_lease(session)
        and (app is None or app.registry.enabled(account.account_id)))

def _binding(session):
    account=session.account
    return (account,account.store,account.characters,getattr(account,'root',None),
        account.uid,account.account_id,Path(account.store.path).resolve(),
        session.shop_session_id,getattr(session,'application',None),getattr(session,'identity',None))

def _same_binding(session,binding):
    current=_binding(session)
    return all(current[i] is binding[i] for i in (0,1,2,3,8,9)) and current[4:8]==binding[4:8]

def handle(session,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x198,0x4c2):return None
    from els_server.storage.manufacture import execute,select_alchemist
    from els_server.domain.manufacture_rules import policy
    if policy()['mode']!='compatibility-v1':return None
    def context():
        return bool(_actor(session) and type(sequence) is int and 1<=sequence<2**32
            and event.performers in ((),(0,)) and event.uid==event.target_uid==2**64-1
            and event.payload_mode==0)
    valid=context()
    binding=_binding(session) if valid else None
    def authorize():
        return bool(context() and _same_binding(session,binding))
    if event.kind==0x4c2:
        try:
            if not valid:raise ValueError('Profession selection state')
            def prepare_selection(wire):
                reply=[Event(0x201,kind=0x4c3,payload=wire)]
                for item in reply:encode_event(item)
                return reply
            wire=select_alchemist(binding[6],binding[4],binding[5],event.payload,
                authorize=authorize,prepare=prepare_selection)
        except (ValueError,sqlite3.Error) as exc:
            if isinstance(exc,sqlite3.Error):logging.getLogger(__name__).exception('Profession transaction rejected')
            wire=selection_ack(-1,ProfessionState(),{},tail_u64=0,tail_i32=0,tail_flag_a=False,tail_flag_b=False)
        return [Event(0x201,kind=0x4c3,payload=wire)]
    try:
        if not valid:raise ValueError('Manufacture session state')
        operation=f'{binding[7]}:{binding[4]}:manufacture:{sequence}'
        def prepare(receipt):
            answer=[Event(0x201,kind=0x199,payload=receipt['response'])]
            if receipt['leveled']:
                answer.append(Event(0x201,kind=0x4c4,payload=level_update(binding[4],receipt['state'],{})))
            if receipt['requires_inventory_sync']:answer.append(session.saved_user_sync())
            if receipt.get('inventory_refresh'):
                from els_server.storage.inventory_management import _updates
                answer.extend(_updates(receipt['inventory_refresh']))
            for item in answer:encode_event(item)
            return answer
        receipt=execute(binding[6],binding[4],binding[5],event.payload,operation,
            now=int(time.time()),authorize=authorize,prepare=prepare)
    except (ValueError,sqlite3.Error) as exc:
        if isinstance(exc,sqlite3.Error):logging.getLogger(__name__).exception('Manufacture transaction rejected')
        ed=session.account.get_reward_balances()['ed'] if valid and authorize() else 0
        return [Event(0x201,kind=0x199,payload=manufacture_ack(result=-1,rewards={},changes=[],ed=ed,profession_xp=0,limit_id=0,limit_value=0))]
    return receipt['prepared_reply']
