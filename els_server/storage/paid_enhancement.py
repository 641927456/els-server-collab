"""Original ordinary enhancement with atomic materials, ED, result and receipt."""
import secrets,sqlite3
from contextlib import closing
from els_server.domain.paid_enhancement import STONES,quote,outcome
from els_server.domain.item_expiration import expired
from els_server.domain.item_locks import locked
from els_server.protocol.paid_enhancement_messages import options,acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.profession_state import require_owner
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances,charge
from els_server.storage.equipment_enhancement import replace


def enhance(path,owner,payload,operation,randbelow=secrets.randbelow,*,account_id=None):
    uid,mode,context,hammer,auto_recovery=options(payload);owner,digest=_identity(owner,0x5ff,payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        if account_id is not None:require_owner(db,owner,account_id)
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        by_position={(i['group'],i['slot']):i for i in before}
        if old is not None:
            item=next((i for i in before if i['uid']==uid),None)
            return [Event(0x201,kind=0x600,payload=acknowledgement(balance['ed'],uid,
                item.get('enhancement',0) if item else 0,changes=current_changes(db,operation,owner,0x5ff,old,before)))]
        item=next((i for i in before if i['uid']==uid),None)
        if item is None:raise ValueError('Enhancement equipment is not owned')
        q=quote(item,mode);materials=[]
        from els_server.domain.advanced_enhancement_materials import catalog
        recovery=None
        if auto_recovery:
            # Original 22468F0 UI template order. Every admission precedes RNG;
            # an unavailable, locked or expired scroll cannot fund this option.
            recovery=next((i for t in catalog()['restoration_templates'] for i in before
                if i['template']==t and i['group']==4 and not expired(i) and not locked(i)),None)
            if recovery is None:raise ValueError('Missing available automatic restoration scroll')
        if mode!=4:
            groups=[STONES]
            if mode in (1,2):groups.append(catalog()['ore_templates' if mode==1 else 'crystal_templates'])
            if hammer:groups.append(catalog()['hammer_templates'])
            for templates in groups:
                material=next((i for t in templates for i in before if i['template']==t and i['group']==4 and not expired(i) and not locked(i)),None)
                if material is None:raise ValueError('Missing enhancement stone or fluorite material')
                materials.append(material)
        # Resolve every deterministic admission before drawing. A retry never
        # redraws; a failed encoder rolls back the entire SQL transaction.
        ed=charge(db,owner,balance,q['ed'])
        result,updated=(1,q['level']+1) if mode==4 else outcome(q['level'],randbelow(10000),mode,hammer)
        if recovery is not None and result==2:
            # 23EF270: outcome 8 shares the no-change presentation and enables
            # SetShow_ResultUseRecoveryItem. 23EB1B0 disables UI only for code 2.
            result,updated=8,q['level'];materials.append(recovery)
        for material in materials:
            if material['count']==1:remove(db,owner,material)
            else:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,material['uid']))
        replace(db,owner,uid,q['level'],updated)
        from els_server.domain.enhancement_progress import after as progress_after
        from els_server.storage.enhancement_progress import replace as replace_progress
        gauge,points=progress_after(item,mode,result,updated)
        replace_progress(db,owner,dict(item,enhancement=updated),gauge,points)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=[(m['group'],m['slot']) for m in materials]+[(item['group'],item['slot'])]
        wire=acknowledgement(ed,uid,updated,result,[(p,current.get(p)) for p in positions])
        _commit(db,operation,digest,owner,0x5ff,positions,before,after)
        return [Event(0x201,kind=0x600,payload=wire)]
