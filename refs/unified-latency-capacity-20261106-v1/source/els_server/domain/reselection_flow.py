"""Native selected-class tickets through the existing career writer/refresh."""
import struct
from els_server.protocol.career_messages import use_ack,selected_use_request


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219:return None
    # Ordinary219 consumers carry no chosen class. Keep their dispatch/read path.
    if len(event.payload)<20 or struct.unpack_from('>i',event.payload,16)[0]==0:return None
    account=s.account;store=getattr(account,'store',None)
    if store is None:return None
    owner=account.uid;account_id=account.account_id;path=store.path
    operation=s.shop_session_id+':'+str(owner)+':'+str(sequence)
    candidate=struct.unpack_from('>Q',event.payload)[0]
    from els_server.storage.read_scope import snapshot_connection
    from els_server.storage.inventory_state import owned_template
    with snapshot_connection(path)as db:
        db.execute('BEGIN')
        selected=owned_template(db,owner,candidate)==135872
        if not selected and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='career_receipts'").fetchone():
            old=db.execute('SELECT item_uid,response FROM career_receipts WHERE operation_id=? AND owner=?',(operation,owner)).fetchone()
            selected=bool(old and old[0]==candidate and len(old[1])>=36 and struct.unpack_from('>i',old[1],-28)[0]==135872)
    if not selected:return None
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    if (not s.item_test or s.client_build!='dx11_260923' or s.role!='game' or s.phase!='town_ready'
        or 0x28 not in s.completed or type(sequence)is not int or not 1<=sequence<2**32
        or event.performers not in ((),(0,)) or event.uid!=2**64-1 or event.target_uid!=2**64-1
        or event.payload_mode!=0 or store.uid!=owner or not current_lease(s)):
        return [use_ack(result=1836)]
    root=account.root;app=getattr(s,'application',None);identity=getattr(s,'identity',None)
    session=s.shop_session_id;location=account.get_location()
    def prepare(db):
        from els_server.storage.item_actor import require_active_character
        from els_server.storage.profession_state import require_owner
        if (s.account is not account or account.store is not store or account.root is not root
            or store.path!=path or (account.uid,account.account_id,s.shop_session_id)!=(owner,account_id,session)
            or getattr(s,'application',None)is not app or getattr(s,'identity',None)is not identity
            or s.role!='game' or s.phase!='town_ready' or getattr(s,'released',False)
            or store.uid!=owner or account.get_location()!=location or not current_lease(s)):
            raise ValueError('Selected career current actor changed')
        require_active_character(db,owner);require_owner(db,owner,account_id)
    def refresh(db,receipt):
        from els_server.storage.seal_quests import load_character
        from els_server.storage.career_shop import notifications
        from els_server.protocol.protocol_codec import encode_event,Event
        current=load_character(db,owner,account_id)
        before=receipt.get('before');after=receipt.get('after')
        projection=current if receipt['replayed']else dict(current,**before)
        events=notifications(db,owner,projection,location,before,after,receipt['replayed'])
        if receipt['replayed']:
            ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0]
            ack=use_ack(template=135872,ed=ed)
        else:ack=Event(0x201,kind=0x21a,payload=receipt['response'])
        events=[ack]+events
        for e in events:encode_event(e)
        return events
    from els_server.storage.careers import use_career_item
    try:
        selected_use_request(event.payload)
        return use_career_item(path,owner,event.payload,operation,refresh,selected=True,prepare=prepare)['prepared_events']
    except ValueError:return [use_ack(result=1836)]
