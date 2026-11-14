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
        and session.role=='game' and session.phase in('town_ready','guild_agit_ready')
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
    if event.event_id==0x202 and event.kind==0x705:
        from els_server.domain.hunter_sphere_flow import handle as sphere_handle
        return sphere_handle(session,event,sequence)
    if event.kind in (0x707,0x9ae):
        from els_server.domain.flask_flow import handle as flask_handle
        return flask_handle(session,event,sequence)
    if event.event_id!=0x202 or event.kind not in (0x198,0x4c2):return None
    from els_server.storage.manufacture import execute,select_profession,MissingMaterials
    from els_server.storage.npc_trade import InsufficientED
    from els_server.storage.inventory_state import InventoryFull
    from els_server.domain.manufacture_rules import policy
    if policy()['mode']!='compatibility-v1':return None
    def context():
        if session.phase=='guild_agit_ready':
            if event.kind!=0x198:return False
            from els_server.protocol.manufacture_messages import manufacture_request
            from els_server.manufacture_data import manufacture_data
            from els_server.storage.manufacture import guild_cooking
            try:
                if not guild_cooking(manufacture_data().recipe(manufacture_request(event.payload).recipe_id)):return False
            except ValueError:return False
        return bool(_actor(session) and type(sequence) is int and 1<=sequence<2**32
            and event.performers in ((),(0,)) and event.uid==event.target_uid==2**64-1
            and event.payload_mode==0)
    valid=context()
    binding=_binding(session) if valid else None
    guild_same=guild_guard=None
    if valid and session.phase=='guild_agit_ready':
        from els_server.domain.guild_agit_flow import bank_capture
        guild_same,guild_guard=bank_capture(session)
    def authorize():
        return bool(context() and _same_binding(session,binding)and(guild_same is None or guild_same()))
    if event.kind==0x4c2:
        try:
            if not valid:raise ValueError('Profession selection state')
            def prepare_selection(wire):
                reply=[Event(0x201,kind=0x4c3,payload=wire)]
                for item in reply:encode_event(item)
                return reply
            wire=select_profession(binding[6],binding[4],binding[5],event.payload,
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
            answer.extend(receipt.get('guild_quest_events',()))
            for item in answer:encode_event(item)
            return answer
        receipt=execute(binding[6],binding[4],binding[5],event.payload,operation,
            now=int(time.time()),authorize=authorize,prepare=prepare,scene_guard=guild_guard)
    except (ValueError,sqlite3.Error) as exc:
        if isinstance(exc,sqlite3.Error):logging.getLogger(__name__).exception('Manufacture transaction rejected')
        ed=session.account.get_reward_balances()['ed'] if valid and authorize() else 0
        return [Event(0x201,kind=0x199,payload=manufacture_ack(result=302 if isinstance(exc,InsufficientED) else 303 if isinstance(exc,MissingMaterials) else 304 if isinstance(exc,InventoryFull) else 1,rewards={},changes=[],ed=ed,profession_xp=0,limit_id=0,limit_value=0))]
    from els_server.domain.gameplay_announcements import publish
    publish(session,receipt.get('announcements',()))
    return receipt['prepared_reply']
