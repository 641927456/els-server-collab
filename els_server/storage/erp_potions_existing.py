"""One real SQL transaction: owned potion decrement, ERP, receipt and encoding."""
from contextlib import closing
import hashlib,sqlite3,struct
from els_server.domain.erp_potions_existing import TEMPLATES,definitions,request
from els_server.storage.resonance_state import owner,snapshot
from els_server.storage.item_actor import require_active_character
from els_server.storage.inventory_state import load_items
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import encode_event

TABLE='erp_potion_use_receipts'

def existing_receipt(db,operation):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone():return None
    return db.execute('SELECT proof,account_id,owner,item_uid,bag_group,slot FROM erp_potion_use_receipts WHERE operation=?',(operation,)).fetchone()

def recognizes(path,uid,payload,operation):
    if type(payload)is not bytes or len(payload)<8:return False
    item_uid=struct.unpack_from('>Q',payload)[0]
    if not 0<item_uid<2**63:return False
    with closing(sqlite3.connect(path,timeout=10))as db:
        row=db.execute('SELECT template FROM inventory_items WHERE uid=? AND owner=?',(item_uid,uid)).fetchone()
        return bool((row and row[0]in TEMPLATES)or existing_receipt(db,operation))

def perform(path,uid,account_id,payload,operation,*,prepare,notices):
    item_uid,quantity=request(payload)
    if type(operation)is not str or not 1<=len(operation)<=200:raise ValueError('ERP potion operation')
    proof=hashlib.sha256(struct.pack('>QQ',account_id,uid)+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        owner(db,uid,account_id);require_active_character(db,uid);prepare(db)
        prior=existing_receipt(db,operation);items=load_items(db,uid)
        balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()
        if balance is None:raise ValueError('ERP potion wallet missing')
        if prior is not None:
            if prior[:4]!=(proof,account_id,uid,item_uid):raise ValueError('ERP potion conflicting retry')
            positions={(prior[4],prior[5])}
            current_item=next((i for i in items if i['uid']==item_uid),None)
            if current_item is not None:positions.add((current_item['group'],current_item['slot']))
            current={(i['group'],i['slot']):i for i in items}
            event=use_ack([(p,current.get(p))for p in sorted(positions)],ed=balance[0])
            current=snapshot(db,uid,account_id);sync,keys=notices(db,current)
            for e in [event,*sync]:encode_event(e)
            prepare(db);require_active_character(db,uid)
            return dict(events=[event,*sync],keys=keys,replayed=True)
        item=next((i for i in items if i['uid']==item_uid),None)
        if item is None or item['template']not in TEMPLATES:raise ValueError('ERP potion owned instance missing')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item);require_unlocked(item)
        if item.get('sealed',False)or quantity>item['count']:raise ValueError('ERP potion sealed or insufficient quantity')
        if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):raise ValueError('ERP potion level99 required')
        current=snapshot(db,uid,account_id);rule=definitions()[item['template']]
        if (not current['enabled']or current['level']<rule['min_level']
            or(rule['max_level']>0 and current['level']>rule['max_level'])or current['revision']>=2**63-1):
            raise ValueError('ERP potion account eligibility/revision')
        from els_server.domain.resonance import limit
        remaining=limit()-current['experience'];xp=rule['experience']
        # Native222E1A4 uses ceil(remaining/perPotion), then clamps to inventory.
        if remaining<=0 or quantity>(remaining+xp-1)//xp:raise ValueError('ERP potion cap quantity')
        amount=min(quantity*xp,remaining)
        position=(item['group'],item['slot'])
        if quantity==item['count']:
            from els_server.storage.item_instances import remove
            remove(db,uid,item)
        elif db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=? AND count=?',(quantity,item_uid,uid,item['count'])).rowcount!=1:
            raise ValueError('ERP potion decrement changed')
        if db.execute('UPDATE account_resonance SET experience=experience+?,revision=revision+1 WHERE account_id=? AND revision=?',(amount,account_id,current['revision'])).rowcount!=1:
            raise ValueError('ERP potion account revision changed')
        db.execute('''CREATE TABLE IF NOT EXISTS erp_potion_use_receipts (
            operation TEXT PRIMARY KEY,proof TEXT NOT NULL,account_id INTEGER NOT NULL,
            owner INTEGER NOT NULL,item_uid INTEGER NOT NULL,bag_group INTEGER NOT NULL,slot INTEGER NOT NULL,
            quantity INTEGER NOT NULL,experience INTEGER NOT NULL)''')
        db.execute('INSERT INTO erp_potion_use_receipts VALUES (?,?,?,?,?,?,?,?,?)',(operation,proof,account_id,uid,item_uid,*position,quantity,amount))
        after=load_items(db,uid);slot=next((i for i in after if(i['group'],i['slot'])==position),None)
        event=use_ack([(position,slot)],item['template'],balance[0])
        current=snapshot(db,uid,account_id);sync,keys=notices(db,current)
        for e in [event,*sync]:encode_event(e)
        prepare(db);require_active_character(db,uid)
        return dict(events=[event,*sync],keys=keys,replayed=False)
