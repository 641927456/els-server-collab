"""Native219 stackable ERP consumer before single-use career dispatch."""
from pathlib import Path
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import encode_event

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219:return None
    account=getattr(s,'account',None);store=getattr(account,'store',None)
    if store is None:return None
    from els_server.storage.erp_potions_existing import recognizes,perform
    operation=s.shop_session_id+':erp-potion-v1:'+str(account.uid)+':'+str(sequence)
    if not recognizes(store.path,account.uid,event.payload,operation):return None
    from els_server.domain.equipment_chip_flow import reset_authority
    root=account.root;app=getattr(s,'application',None);identity=getattr(s,'identity',None)
    registry=getattr(app,'registry',None);local_app=getattr(s,'_chip_reset_local_application',None)
    path=Path(store.path).resolve();uid=account.uid;account_id=account.account_id;session=s.shop_session_id
    def prepare(db):
        # Reuse the accepted exact Application/registry/root/save graph guard;
        # the Application local lifecycle marker is shared and already present.
        reset_authority(s)
        if (not s.item_test or s.client_build!='dx11_260923' or s.phase!='town_ready'
            or not {0x28,0x225,0x227}<=s.completed
            or type(sequence)is not int or not 1<=sequence<2**32
            or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
            or s.account is not account or account.store is not store or account.root is not root
            or getattr(s,'application',None)is not app or getattr(s,'identity',None)is not identity
            or getattr(app,'registry',None)is not registry or getattr(s,'_chip_reset_local_application',None)is not local_app
            or(account.uid,account.account_id,s.shop_session_id)!=(uid,account_id,session)
            or Path(store.path).resolve()!=path):raise ValueError('ERP potion current actor/context')
    def notices(db,current):
        from els_server.domain.resonance_allocation_flow import prepare as page_prepare
        p,state=page_prepare(db,s)
        messages=[s.saved_user_sync(resonance_snapshot=current),state.notice()]
        for message in messages:encode_event(message)
        revision=p.pages.read(account_id,uid).revision
        return messages,((account_id,current['revision'],uid),(account_id,uid,current['revision'],(revision,)))
    try:
        result=perform(path,uid,account_id,event.payload,operation,prepare=prepare,notices=notices)
        s.resonance_sync_key,s.resonance_page_sync_key=result['keys']
        return result['events']
    except ValueError:return [use_ack(result=-1)]
