"""One complete owned instance in durable mail escrow, within the caller's tx.

Only the current server item schema is supported. A missing/unknown seal or
external instance state never grants permission to cross character ownership.
The source snapshot is immutable audit data; it is never used to replay a grant.
"""
import json,struct
from els_server.storage.game_mail import MailError


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS player_mail_items (
        mail_id INTEGER PRIMARY KEY REFERENCES game_mail(id),
        item_uid INTEGER NOT NULL,source_json TEXT NOT NULL,item_json TEXT NOT NULL,
        expires_at INTEGER,claimed_at INTEGER,claimed_uid INTEGER,
        positions_json TEXT NOT NULL DEFAULT '[]',moved_to INTEGER,expired_at INTEGER)''')
    db.execute('''CREATE UNIQUE INDEX IF NOT EXISTS player_mail_active_item
        ON player_mail_items(item_uid) WHERE claimed_at IS NULL AND moved_to IS NULL AND expired_at IS NULL''')
    db.execute('''CREATE TABLE IF NOT EXISTS player_mail_send_items (
        operation TEXT PRIMARY KEY,positions_json TEXT NOT NULL)''')


def _transaction(db):
    if not db.in_transaction:raise MailError('Attachment transfer requires transaction')


def _snapshot(item):
    from els_server.domain.inventory_items import validate_item
    return json.dumps(validate_item(item),sort_keys=True,separators=(',',':'))


def _known_links(db,uid):
    # An upgraded save may carry a new cascading child that the frozen
    # item_instances adapter cannot reconstruct. Reject before removing it.
    supported={'equipment_attributes','equipment_durability','equipment_enhancement',
        'item_expiration','item_locks','equipment_options','equipment_identification',
        'equipment_enhancement_progress','item_seals','artifact_equipment_state'}
    quote=lambda s:'"'+s.replace('"','""')+'"'
    for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        if table in supported:continue
        for fk in db.execute('PRAGMA foreign_key_list('+quote(table)+')'):
            if fk[2]=='inventory_items' and db.execute(
                    'SELECT 1 FROM '+quote(table)+' WHERE '+quote(fk[3])+'=? LIMIT 1',(uid,)).fetchone():
                raise MailError('Attachment has unsupported linked state')


def qualify(item,*,now):
    """Static pinned 2DDAA00 -> 2DE6950 eligibility, supported state only.

    Bound/sealed transfers remain closed pending a CN general unsealing rule.
    Native eligibility is necessary; server container and state checks are also
    enforced. The server owns all fields, including postage's template price.
    """
    from els_server.domain.inventory_items import validate_item,TEMPLATE_BAG_GROUPS
    from els_server.game_data import client_data
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    item=validate_item(item);definition=client_data().item(item['template'])
    if item.get('wardrobe_hanger',False):raise MailError('Wardrobe hanger is bound and cannot be mailed')
    if item['group'] in (9,24,21) or item['group']!=TEMPLATE_BAG_GROUPS[item['template']]:
        raise MailError('Unequip item or remove character-only entitlement before mailing')
    require_current(item,now=now);require_unlocked(item,now=now)
    if definition['flags4']&32:raise MailError('Template forbids mail attachment')
    if definition['flags4']&2 and not item.get('sealed',False):
        raise MailError('Template requires verified sealed transfer')
    if item.get('sealed',False):raise MailError('Sealed transfer conversion is not verified')
    if definition['record'][0xd7]==255:raise MailError('Special unlimited-seal template is not verified')
    if item['metadata'] in (0,1) and not {'sealed','seal_used'}<=set(item):
        raise MailError('Equipment needs explicit persisted seal state')
    if item.get('seal_used',0)>definition['record'][0xd7]:
        raise MailError('Persisted seal usage exceeds template evidence')
    if item.get('enhancement',0)<0:raise MailError('Broken item cannot be mailed')
    if item['metadata']==1:
        maximum=struct.unpack_from('<h',definition['record'],0xc8)[0]
        if 'durability' not in item or item['durability']<maximum:
            raise MailError('Repair equipment before mailing')
    # Fixed constructor/entry converter: DTO+34E, +37C and entry+3FF
    # are unsupported dynamic restrictions. The current encoder only emits
    # their pinned zero defaults; unknown new instance keys fail validate_item.
    from els_server.domain.inventory_items import fixture
    seed=fixture()
    for offset,zero in ((0x34e,'0000'),(0x37c,'00')):
        field=next(f for f in seed['fields'] if int(f['offset'],0)==offset)
        if field['wire_hex']!=zero:raise MailError('Unsupported mail restriction seed')
    price=struct.unpack_from('<i',definition['record'],0x1c)[0]
    if price<0:raise MailError('Invalid template postage price')
    return price


def take(db,owner,item_uid,quantity,*,now):
    _transaction(db)
    if type(item_uid) is not int or not 0<item_uid<2**63 or type(quantity) is not int or not 1<=quantity<=99:
        raise MailError('Invalid attachment instance or quantity')
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_instances import remove,insert,next_uid
    item=next((i for i in load_items(db,owner) if i['uid']==item_uid),None)
    if item is None or quantity>item['count']:raise MailError('Attachment not owned or insufficient quantity')
    price=qualify(item,now=now)
    _known_links(db,item_uid)
    if db.execute('''SELECT 1 FROM player_mail_items WHERE item_uid=? AND claimed_at IS NULL
        AND moved_to IS NULL AND expired_at IS NULL''',(item_uid,)).fetchone():
        raise MailError('Attachment already in mail escrow')
    source=dict(item);remaining=item['count']-quantity
    remove(db,owner,item)
    if remaining:insert(db,owner,dict(item,count=remaining))
    moved=dict(item,count=quantity,uid=next_uid(db) if remaining else item_uid)
    # CN enhancement guide explicitly resets both counters when mail is sent.
    # Keep the pre-transfer state separately for audit, never for retry grants.
    moved.pop('enhancement_gauge',None)
    moved.pop('enhancement_guarantee',None)
    return source,moved,price,[(item['group'],item['slot'])]


def put(db,mail_id,source,item):
    _transaction(db)
    from els_server.storage.item_instances import uid_in_use
    if uid_in_use(db,item['uid']):raise MailError('Escrow UID remains in another container')
    db.execute('''INSERT INTO player_mail_items
        (mail_id,item_uid,source_json,item_json,expires_at) VALUES (?,?,?,?,?)''',
        (mail_id,item['uid'],_snapshot(source),_snapshot(item),item.get('expires_at')))


def retire_expired(db,now):
    _transaction(db)
    # Natural item expiry is independent of the letter's display deadline.
    # Retain the original JSON as an audit tombstone, never recreate the item.
    rows=db.execute('''SELECT mail_id FROM player_mail_items WHERE claimed_at IS NULL
        AND moved_to IS NULL AND expired_at IS NULL AND expires_at<? ORDER BY mail_id LIMIT 100''',(now,)).fetchall()
    for (mid,) in rows:db.execute('UPDATE player_mail_items SET expired_at=? WHERE mail_id=?',(now,mid))
    return len(rows)


def pending(db,mail_id,*,now):
    row=db.execute('''SELECT item_uid,item_json,expires_at FROM player_mail_items WHERE mail_id=?
        AND claimed_at IS NULL AND moved_to IS NULL AND expired_at IS NULL''',(mail_id,)).fetchone()
    if row is None or row[2] is not None and row[2]<now:return None
    from els_server.domain.inventory_items import validate_item
    item=validate_item(json.loads(row[1]))
    if item['uid']!=row[0] or item.get('expires_at')!=row[2]:raise MailError('Corrupt attachment escrow')
    return item


def move_return(db,source_mail,return_mail,*,now):
    _transaction(db);item=pending(db,source_mail,now=now)
    if item is None:return
    row=db.execute('SELECT source_json,item_json,expires_at FROM player_mail_items WHERE mail_id=?',(source_mail,)).fetchone()
    db.execute('UPDATE player_mail_items SET moved_to=? WHERE mail_id=?',(return_mail,source_mail))
    db.execute('''INSERT INTO player_mail_items
        (mail_id,item_uid,source_json,item_json,expires_at) VALUES (?,?,?,?,?)''',
        (return_mail,item['uid'],*row))


def changes(db,owner,positions):
    if not positions:return []
    from els_server.storage.inventory_state import load_items
    current={(i['group'],i['slot']):i for i in load_items(db,owner)}
    return [(tuple(p),current.get(tuple(p))) for p in positions]


def receipt_changes(db,owner,positions,*,affected=None):
    # Historic claim receipts contain positions only: they cannot identify a
    # later-moved merged stack. Refresh the owner's current inventory in that
    # case, retaining old slots to clear or replace them. Never grant snapshots.
    if (not isinstance(positions,list) or not positions or
            any(not isinstance(p,list) or len(p)!=2 or
                any(type(v) is not int for v in p) or
                not 0<=p[0]<=255 or not 0<=p[1]<=32767 for p in positions)):
        raise MailError('Attachment receipt positions')
    points=list(dict.fromkeys(map(tuple,positions)))
    from els_server.storage.inventory_state import load_items
    items=load_items(db,owner)
    points.extend((i['group'],i['slot']) for i in items
                  if (affected is None or i['uid'] in affected)
                  and (i['group'],i['slot']) not in points)
    current={(i['group'],i['slot']):i for i in items}
    return [(p,current.get(p)) for p in points]


def sent_changes(db,owner,operation):
    row=db.execute('''SELECT r.sender_uid,s.positions_json,m.source_json
        FROM player_mail_send_items s JOIN player_mail_receipts r ON r.operation=s.operation
        LEFT JOIN player_mail_items m ON m.mail_id=r.mail_id WHERE s.operation=?''',(operation,)).fetchone()
    if row is None:return []
    if row[0]!=owner:raise MailError('Attachment send receipt owner')
    try:
        positions=json.loads(row[1]);source=json.loads(row[2])
        if (not isinstance(source,dict) or type(source.get('uid')) is not int
                or not 0<source['uid']<2**63 or
                [source.get('group'),source.get('slot')] not in positions):
            raise MailError('Attachment send source history')
    except (TypeError,json.JSONDecodeError) as exc:
        raise MailError('Attachment send receipt format') from exc
    return receipt_changes(db,owner,positions,affected={source['uid']})


def claim(db,owner,mail_id,*,now):
    _transaction(db)
    old=db.execute('SELECT claimed_at,claimed_uid,positions_json FROM player_mail_items WHERE mail_id=?',(mail_id,)).fetchone()
    if old is None:return []
    if old[0] is not None:return receipt_changes(db,owner,json.loads(old[2])) if old[1]==owner else []
    item=pending(db,mail_id,now=now)
    if item is None:
        db.execute('''UPDATE player_mail_items SET expired_at=COALESCE(expired_at,?) WHERE mail_id=?
            AND claimed_at IS NULL AND moved_to IS NULL AND expires_at<?''',(now,mail_id,now))
        return []
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_instances import insert,uid_in_use
    from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    from els_server.storage.bag_capacity import allowances
    if uid_in_use(db,item['uid']):raise MailError('Escrow instance already belongs to another container')
    before=load_items(db,owner);group=TEMPLATE_BAG_GROUPS[item['template']]
    maximum=TEMPLATE_MAX_STACKS[item['template']];remaining=item['count'];positions=[]
    signature=lambda i:{k:v for k,v in i.items() if k not in ('uid','count','group','slot')}
    for target in before:
        if remaining and target['group']==group and maximum>1 and signature(target)==signature(item):
            added=min(remaining,maximum-target['count'])
            if added:
                db.execute('UPDATE inventory_items SET count=count+? WHERE uid=? AND owner=?',(added,target['uid'],owner))
                remaining-=added;positions.append((group,target['slot']))
    if remaining:
        occupied={i['slot'] for i in before if i['group']==group};limit=allowances(db,owner)[group]
        slot=next((n for n in range(limit) if n not in occupied),None)
        if slot is None:raise MailError('Attachment needs free inventory space')
        insert(db,owner,dict(item,count=remaining,group=group,slot=slot));positions.append((group,slot))
    db.execute('UPDATE player_mail_items SET claimed_at=?,claimed_uid=?,positions_json=? WHERE mail_id=?',
        (now,owner,json.dumps(positions),mail_id))
    return changes(db,owner,positions)
