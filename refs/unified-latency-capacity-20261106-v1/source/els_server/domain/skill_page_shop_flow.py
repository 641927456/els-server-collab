"""One current local ED instant service; unrelated shop purchases unchanged."""
from pathlib import Path
from els_server.domain.skill_page_shop import SKU
from els_server.protocol.shop_messages import ed_purchase_request,ed_purchase_ack

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x80f:return None
    try:products=ed_purchase_request(event.payload)
    except ValueError:return None
    if not any(sku==SKU for sku,n in products):return None
    from els_server.domain.equipment_chip_flow import reset_authority
    account=s.account;store=account.store;root=account.root
    app=getattr(s,'application',None);identity=getattr(s,'identity',None);registry=getattr(app,'registry',None)
    local_app=getattr(s,'_chip_reset_local_application',None)
    uid=account.uid;account_id=account.account_id;session=s.shop_session_id
    path=Path(store.path).resolve()if store is not None else None
    def prepare(db):
        reset_authority(s)
        if (not s.shop_test or not s.item_test or s.client_build!='dx11_260923'
            or s.phase!='town_ready' or not s.ed_catalog_loaded or not {0x28,0x225,0x227}<=s.completed
            or type(sequence)is not int or not 1<=sequence<2**32
            or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
            or s.account is not account or account.store is not store or account.root is not root
            or getattr(s,'application',None)is not app or getattr(s,'identity',None)is not identity
            or getattr(app,'registry',None)is not registry or getattr(s,'_chip_reset_local_application',None)is not local_app
            or(account.uid,account.account_id,s.shop_session_id)!=(uid,account_id,session)
            or Path(store.path).resolve()!=path):raise ValueError('Skill page shop current actor/context')
    try:
        prepare(None)  # refuse incomplete frontend/roster graphs before SQL open
        from els_server.storage.skill_page_shop import purchase
        return purchase(path,uid,account_id,event.payload,session+':skill-page-shop-v1:'+str(uid)+':'+str(sequence),prepare=prepare)
    except ValueError:return [ed_purchase_ack(-1,[],0)]
