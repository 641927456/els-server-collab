"""Verified native expansion only; current App identity and NPC town required."""
from pathlib import Path
from els_server.protocol import tenebros_capacity_messages as wire


def context(s,*,npc=False):
    from els_server.domain.equipment_chip_flow import reset_authority
    reset_authority(s)
    if (s.role!='game' or s.phase!='town_ready' or s.client_build!='dx11_260923'
        or not s.item_test or getattr(s,'released',False) or not {0x28,0x225,0x227}<=s.completed
        or (npc and s.active_map!=20013)):
        raise ValueError('Tenebros selected town actor')


def selected(s,*,npc=False):
    context(s,npc=npc)
    account=s.account;store=account.store;root=account.root
    app=getattr(s,'application',None);local_app=getattr(s,'_chip_reset_local_application',None)
    identity=getattr(s,'identity',None);registry=getattr(app,'registry',None)
    path=Path(store.path).resolve();owner=account.uid;account_id=account.account_id
    session=s.shop_session_id;town=s.active_map
    def prepare(db):
        context(s,npc=npc)
        if (s.account is not account or account.store is not store or account.root is not root
            or getattr(s,'application',None) is not app or getattr(s,'identity',None) is not identity
            or getattr(s,'_chip_reset_local_application',None) is not local_app
            or getattr(app,'registry',None) is not registry
            or (account.uid,account.account_id,s.shop_session_id,s.active_map)!=(owner,account_id,session,town)
            or Path(store.path).resolve()!=path):raise ValueError('Tenebros selected actor changed')
    return path,owner,account_id,prepare


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x9f2 or s.client_build!='dx11_260923':return None
    try:
        wire.request(event.payload)
        if (type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
            or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
            raise ValueError('Tenebros envelope')
        path,owner,account_id,prepare=selected(s,npc=True)
        from els_server.storage.tenebros_capacity import perform
        operation=s.shop_session_id+':tenebros-capacity-v1:'+str(account_id)+':'+str(owner)+':'+str(sequence)
        return perform(path,owner,account_id,event.payload,operation,prepare=prepare)
    except ValueError:
        # Native nonzero-result branch never applies these sentinel fields.
        return [wire.acknowledge(result=2005)]


def synchronize(s,messages):
    # A single native 9F1 projects shared capacity and this character's effects.
    # Sending the former zero vector after storage would erase the client view.
    from els_server.domain.tenebros_storage_flow import synchronize as synchronize_storage
    return synchronize_storage(s,messages)
