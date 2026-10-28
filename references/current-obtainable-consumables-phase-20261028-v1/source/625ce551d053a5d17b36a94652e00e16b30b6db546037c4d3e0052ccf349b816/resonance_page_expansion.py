"""Owned712413 -> one new native ERP page, in the existing inventory writer.

Uses the current profile's already-reviewed local one-point-per-earned-level
policy, only for the existing zero-opaque/no-temporary-points profile. It does
not grant EXP, edit any prior page, select the new page, or open another source.
"""
from contextlib import closing
from dataclasses import replace
import functools,hashlib,sqlite3,struct,time
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove

TEMPLATE=712413
ITEM_SHA='9da990fe2e9e8a83d89bfa48ce07054f586f0bfff5388374731d7675d81e264f'

@functools.lru_cache(maxsize=1)
def definition():
    from els_server.game_data import client_data
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    item=client_data().item(TEMPLATE)
    if(hashlib.sha256(item['record']).hexdigest()!=ITEM_SHA or item['item_type']!=7
       or(item['metadata'],VERIFIED_TEMPLATES.get(TEMPLATE),TEMPLATE_BAG_GROUPS.get(TEMPLATE),TEMPLATE_MAX_STACKS.get(TEMPLATE))!=(0,0,4,1)):
        raise ValueError('Current ERP page expansion item identity')

def perform(path,owner,account_id,payload,operation,*,prepare,now=None):
    source_uid=use_request(payload);owner,digest=_identity(owner,0x219,b'owned712413:'+payload,operation)
    if not callable(prepare):raise ValueError('ERP page expansion current actor guard required')
    definition()
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    from els_server.storage.resonance_state import snapshot as legacy
    from els_server.domain.resonance_allocation_flow import profiles
    from els_server.storage.resonance_2026_pages import ResonancePage
    def authority(db):
        prepare(db);require_active_character(db,owner);require_owner(db,owner,account_id)
        if db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()!=(99,):raise ValueError('ERP page expansion requires full-level character')
        state=legacy(db,owner,account_id)
        if not state['enabled']:raise ValueError('ERP page expansion requires unlocked resonance')
        return state
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');original_legacy=authority(db)
        before=load_items(db,owner);old=_previous(db,operation,digest)
        item=next((i for i in before if i['uid']==source_uid),None)
        if old is None and(item is None or item['template']!=TEMPLATE):return None
        if old is None:
            if(item['metadata'],item['count'],item['group'])!=(0,1,4)or item.get('sealed',False):raise ValueError('ERP page expansion owned singleton required')
            from els_server.domain.item_expiration import require_current
            from els_server.domain.item_locks import require_unlocked
            moment=int(time.time())if now is None else now
            require_current(item,now=moment);require_unlocked(item,now=moment)
        p=profiles(db);p.initialize();p.accounts.migrate_dominated_legacy(account=account_id,character=owner)
        state=p.synchronize(account=account_id,character=owner);pages=p.pages.read(account_id,owner);metadata=p._metadata(account_id,owner)
        if not pages.enabled or metadata[1]!=(0,0,0,0,0):raise ValueError('ERP expansion requires existing ordinary no-temporary profile')
        if any(page.available_points+sum(value for stat,value in page.points)!=state.level for page in pages.pages):raise ValueError('ERP expansion earned-point budget is not authoritative')
        balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if balance is None:raise ValueError('ERP expansion balance missing')
        if old is not None:
            # Never send an obsolete page count/allocation snapshot on retry.
            if not db.execute('SELECT 1 FROM resonance2026_page_receipts WHERE character=?AND operation=?',(owner,operation)).fetchone():raise ValueError('ERP expansion lost its committed page receipt')
            changes=current_changes(db,operation,owner,0x219,old,before)
            events=[use_ack(changes,TEMPLATE,balance[0]),state.notice()]
        else:
            if len(pages.pages)>=4:raise ValueError('ERP page expansion maximum is four')
            new_id=len(pages.pages)+1
            zero=tuple((stat.stat_id,0)for stat in p.pages.rules.stats)
            def change(current,revision):
                if current!=pages:raise ValueError('ERP page source revision changed')
                return replace(current,revision=revision,pages=current.pages+(ResonancePage(new_id,state.level,zero),))
            p.pages.mutate(account=account_id,character=owner,operation=operation,expected_revision=pages.revision,
                kind='owned712413-native-page-expansion-v1',inputs=[payload.hex(),source_uid,ITEM_SHA,state.level],change=change)
            remove(db,owner,item);after=load_items(db,owner);state=p.synchronize(account=account_id,character=owner)
            events=[use_ack([((item['group'],item['slot']),None)],TEMPLATE,balance[0]),state.notice()]
        for event in events:encode_event(event)
        if authority(db)!=original_legacy:raise ValueError('ERP expansion original account authority changed')
        current=p.pages.read(account_id,owner)
        if old is None:_commit(db,operation,digest,owner,0x219,[(item['group'],item['slot'])],before,after)
        return dict(events=events,page_revision=current.revision,legacy_revision=original_legacy['revision'])
