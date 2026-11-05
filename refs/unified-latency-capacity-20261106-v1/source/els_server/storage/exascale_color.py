"""Atomic owned color conversion; one voucher, no ED under explicit local policy."""
import sqlite3
from pathlib import Path
from contextlib import closing
from els_server.domain.exascale_color_rules import recolor,voucher_rule
from els_server.domain.exascale_color_inventory import policy
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.exascale_color_messages import request,acknowledgement
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_options import replace
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove

def perform(path,owner,payload,operation,*,account_id=None,encode=acknowledgement):
    uid,color=request(payload);owner,digest=_identity(owner,0x8d1,payload,operation)
    if policy()['quantity_per_use']!=1 or policy()['ed_per_use']!=0:raise ValueError('Unqualified color local policy')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM characters WHERE uid=?',(owner,)).fetchone() is None:raise ValueError('Unknown color character')
        if account_id is not None:
            from els_server.storage.profession_state import require_owner
            require_owner(db,owner,account_id)
        old=_previous(db,operation,digest);before=load_items(db,owner)
        if old is not None:return [encode(uid,current_changes(db,operation,owner,0x8d1,old,before))]
        item=next((i for i in before if i['uid']==uid),None)
        if item is None or item['group']!=1 or item['count']!=1 or item.get('identified') is False or item.get('sealed'):raise ValueError('Owned identified unequipped color armor required')
        require_current(item);require_unlocked(item)
        rule=voucher_rule(item['template']);previous=item.get('option_groups',{});updated=recolor(item['template'],previous,color)
        candidates=[]
        for source in before:
            if source['group']!=4 or source['template'] not in rule['templates'] or source.get('sealed'):continue
            try:require_current(source);require_unlocked(source)
            except ValueError:continue
            candidates.append(source)
        if not candidates:raise ValueError('No usable matching color voucher')
        source=min(candidates,key=lambda i:(i.get('expires_at',2**63-1),rule['templates'].index(i['template']),i['slot'],i['uid']))
        positions=[(item['group'],item['slot']),(source['group'],source['slot'])]
        if source['count']==1:remove(db,owner,source)
        elif db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',(source['uid'],owner,source['count'])).rowcount!=1:raise ValueError('Stale color voucher count')
        replace(db,owner,uid,previous,updated)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        # Serialize before committing either the decrement or operation receipt.
        response=[encode(uid,[(p,current.get(p)) for p in positions])]
        _commit(db,operation,digest,owner,0x8d1,positions,before,after)
        return response
