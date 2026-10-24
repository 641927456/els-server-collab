"""Atomic immediate shop service sharing the existing canonical skill pages."""
from contextlib import closing
import hashlib,sqlite3,struct
from els_server.domain.skill_page_shop import SKU,offer
from els_server.protocol.shop_messages import ed_purchase_request,ed_purchase_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.item_actor import require_active_character
from els_server.storage.resonance_state import owner as require_owner
from els_server.storage import ordinary_skill_pages as pages
from els_server.storage.reward_state import validate_balances

def purchase(path,uid,account,payload,operation,*,prepare):
    if ed_purchase_request(payload)!=((SKU,1),):raise ValueError('Buy one instant skill page service alone')
    rule=offer()
    if type(operation)is not str or not 1<=len(operation)<=200:raise ValueError('Skill page shop operation')
    proof=hashlib.sha256(pages.POLICY.encode()+struct.pack('>QQ',account,uid)+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        prepare(db);require_owner(db,uid,account);require_active_character(db,uid)
        pages._actor(db,uid,account);state=pages.view(db,uid)
        balance=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
        prior=db.execute('SELECT owner,account_id,proof FROM skill_page_shop_receipts WHERE operation=?',(operation,)).fetchone()if pages.present(db,'skill_page_shop_receipts')else None
        if prior is not None:
            if prior!=(uid,account,proof):raise ValueError('Conflicting skill page shop retry')
        else:
            if state['count']>=pages.MAX_PAGES or state['revision']>=2**63-1:raise ValueError('Skill page shop local maximum/revision')
            if balance['ed']<rule['price']or balance['revision']>=2**63-1:raise ValueError('Skill page shop funds/revision')
            pages.ensure(db)
            count=state['count']+1
            pages._save_snapshot(db,uid,count,(0,)*22,{},((0,0),)*3)
            db.execute('INSERT INTO ordinary_skill_page_states VALUES(?,?,?,?) ON CONFLICT(owner)DO UPDATE SET page_count=excluded.page_count,revision=excluded.revision',(uid,count,state['selected'],state['revision']+1))
            db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=?',(rule['price'],uid))
            db.execute('''CREATE TABLE IF NOT EXISTS skill_page_shop_receipts (
                operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),
                account_id INTEGER NOT NULL,proof TEXT NOT NULL)''')
            db.execute('INSERT INTO skill_page_shop_receipts VALUES(?,?,?,?)',(operation,uid,account,proof))
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
        # Reuse the complete current55B serializer and career-safe projection.
        # The existing selected484 preparation is encoded but not transmitted.
        notice=pages._reply(db,uid,account,0x483)[-1]
        events=[ed_purchase_ack(0,[],ed),notice]
        for event in events:encode_event(event)
        prepare(db);require_owner(db,uid,account);require_active_character(db,uid)
        return events
