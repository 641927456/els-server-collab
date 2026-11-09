"""Recover a paid, owned buy-only transcendence book before role initialization."""
from contextlib import closing
import json,sqlite3


def recover(path,uid,account_id,*,prepare):
    from els_server.storage.character_schema import character_uid
    uid=character_uid(uid)
    if type(account_id) is not int or account_id<1:raise ValueError('Career recovery account identity')
    from els_server.storage.characters import Characters
    from els_server.storage.careers import apply_transition
    from els_server.domain.careers import transition
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    from els_server.storage.read_scope import snapshot_connection
    with snapshot_connection(path) as probe:
        probe.execute('BEGIN')
        if probe.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):
            raise ValueError('Career recovery owner mismatch')
        row=probe.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
        try:transition(Characters._row(row),288319)
        except ValueError:return dict(status='not_eligible')
    with closing(sqlite3.connect(path,timeout=10)) as db:
        with write_transaction(db):
            if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):
                raise ValueError('Career recovery owner mismatch')
            row=db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
            character=Characters._row(row)
            try:transition(character,288319)
            except ValueError:return dict(status='not_eligible')
            books=[i for i in load_items(db,uid) if i['template']==288319 and i['group']==4 and i['count']==1]
            if not books:return dict(status='no_owned_paid_book')
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='shop_purchase_receipts'").fetchone():
                return dict(status='no_paid_purchase')
            receipts={}
            sql='SELECT operation_id,cost,items_json FROM shop_purchase_receipts WHERE cost>0'
            args=()
            if uid!=1001:sql+=' AND operation_id GLOB ?';args=(str(uid)+':*',)
            for operation,cost,raw in db.execute(sql,args):
                if uid!=1001 and not operation.startswith(str(uid)+':'):continue
                prefix,separator,_=operation.partition(':')
                if uid==1001 and separator and prefix.isdecimal() and int(prefix)>=1001:continue
                for item in json.loads(raw):
                    if item.get('template')==288319 and item.get('count')==1 and item.get('group')==4:
                        receipts[item['uid']]=operation
            for item in books:
                if item['uid'] not in receipts or item['template']!=288319 or item['group']!=4 or item['count']!=1:continue
                try:require_current(item);require_unlocked(item)
                except ValueError:continue
                # All eligibility, skill migration, consumption, proof and wire
                # validation share this transaction. ED and old receipts stay intact.
                before,after=apply_transition(db,uid,288319)
                prepare(db,before,after,False)
                from els_server.storage.item_expiration import forget as forget_expiration
                from els_server.storage.item_locks import forget as forget_lock
                forget_expiration(db,item['uid']);forget_lock(db,item['uid'])
                db.execute('DELETE FROM inventory_items WHERE owner=? AND uid=?',(uid,item['uid']))
                db.execute('CREATE TABLE IF NOT EXISTS career_purchase_recoveries (item_uid INTEGER PRIMARY KEY, owner INTEGER NOT NULL, source_operation TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL)')
                db.execute('INSERT INTO career_purchase_recoveries VALUES (?,?,?,?,?)',
                           (item['uid'],uid,receipts[item['uid']],json.dumps(before,sort_keys=True),json.dumps(after,sort_keys=True)))
                return dict(status='recovered',item_uid=item['uid'],source_operation=receipts[item['uid']])
            return dict(status='no_owned_paid_book')

from els_server.storage.sqlite_timing import write_transaction
