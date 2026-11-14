"""Current wedding reservations on the immutable, accepted couple generation.

The caller owns one writer transaction, session lease and real mail/reward
factory. Ring removal, reservation, invitations and that factory commit together.
"""
from datetime import datetime, timedelta
import hashlib
import json

from els_server.domain.item_expiration import CLIENT_ZONE, require_current
from els_server.domain.item_locks import require_unlocked
from els_server.domain.relationship_rules import MALE, FEMALE, VOW_HALL, VOW_MARK, REMINDER_MARK, VOW_TICKET
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import relationships
from els_server.storage.inventory_state import load_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.storage.profession_state import require_owner

BOOKINGS = 'native_wedding_bookings'
INVITES = 'native_wedding_invites'
SCHEMAS = {
    BOOKINGS: '''CREATE TABLE native_wedding_bookings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pair_id TEXT NOT NULL REFERENCES native_couple_pairs_v1(id),
        owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,
        groom INTEGER NOT NULL REFERENCES characters(uid),bride INTEGER NOT NULL REFERENCES characters(uid),
        hall INTEGER NOT NULL CHECK(hall BETWEEN 2 AND 5),
        officiant INTEGER NOT NULL CHECK(officiant BETWEEN 0 AND 4),
        ends_at INTEGER NOT NULL,message TEXT NOT NULL,password TEXT NOT NULL,
        public INTEGER NOT NULL CHECK(public IN(0,1)),
        reserved_seats INTEGER NOT NULL CHECK(reserved_seats BETWEEN 0 AND 30),
        created_at INTEGER NOT NULL,ring_json TEXT NOT NULL,
        operation TEXT NOT NULL UNIQUE,request_hash TEXT NOT NULL,payload BLOB NOT NULL,
        started_at INTEGER,finished_at INTEGER,canceled_at INTEGER)''',
    INVITES: '''CREATE TABLE native_wedding_invites(
        reservation INTEGER NOT NULL REFERENCES native_wedding_bookings(id),
        guest INTEGER NOT NULL REFERENCES characters(uid),created_at INTEGER NOT NULL,
        PRIMARY KEY(reservation,guest))''',
}


def present(db):
    found = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name IN(?,?)",
                            (BOOKINGS, INVITES)))
    if found and found != SCHEMAS:
        raise ValueError('Unknown or partial wedding schema')
    if db.execute("SELECT 1 FROM sqlite_master WHERE tbl_name IN(?,?) AND "
                  "(type='trigger' OR(type='index' AND sql IS NOT NULL)) LIMIT 1",
                  (BOOKINGS, INVITES)).fetchone():
        raise ValueError('Unreviewed wedding writer extension')
    return bool(found)


def initialize(db):
    if not db.in_transaction:
        raise ValueError('Wedding schema requires writer transaction')
    if not present(db):
        for sql in SCHEMAS.values():db.execute(sql)
    present(db)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _digest(owner, payload):
    return hashlib.sha256(str(owner).encode()+b':887:'+payload).hexdigest()


def pairing(db, owner, account):
    saved = relationships.snapshot(db, owner, account)
    if saved is None:
        raise ValueError('Wedding requires an accepted current couple')
    pair = db.execute('SELECT a,b,a_account,b_account FROM native_couple_pairs_v1 WHERE id=?',
                      (saved['pair_id'],)).fetchone()
    if pair is None:
        raise ValueError('Wedding accepted couple generation missing')
    peer = saved['peer_uid']
    peer_account = pair[3] if pair[0] == owner else pair[2]
    other = relationships.snapshot(db, peer, peer_account)
    if other is None or (other['pair_id'], other['peer_uid']) != (saved['pair_id'], owner):
        raise ValueError('Wedding reciprocal couple generation changed')
    return saved, peer_account


def married_since(db, pair_id):
    from els_server.storage.wedding_ceremonies import marriage
    return marriage(db,pair_id)


def _record(db, reservation):
    cursor = db.execute('SELECT *FROM native_wedding_bookings WHERE id=?',(reservation,))
    value = cursor.fetchone()
    if value is None:
        raise ValueError('Wedding reservation missing')
    row = dict(zip((c[0] for c in cursor.description), value))
    # Old booking schema stores wedding halls 2–5. The immutable paid item
    # distinguishes private vows, whose native hall is projected as 6.
    if ring_template(row) in (VOW_MARK, REMINDER_MARK):
        row['hall'] = VOW_HALL
    names = dict(db.execute('SELECT uid,name FROM characters WHERE uid IN(?,?)',
                            (row['groom'],row['bride'])))
    if len(names) != 2:
        raise ValueError('Wedding saved participants missing')
    row.update(groom_name=names[row['groom']],bride_name=names[row['bride']],
               invited=db.execute('SELECT COUNT(*) FROM native_wedding_invites WHERE reservation=?',
                                   (reservation,)).fetchone()[0],
               success=row['finished_at'] is not None,deleted=row['canceled_at'] is not None,
               room=0,guests=0)
    return row


def ring_template(row):
    return json.loads(row['ring_json'])['template']


def _valid_ticket(item,now):
    if (item['group'],item['metadata'])!=(4,0)or item['template']not in(277151,277152,VOW_TICKET):
        raise ValueError('Wedding personalized ticket must be in inventory')
    require_current(item,now=now);require_unlocked(item,now=now)
    if item.get('sealed',False):raise ValueError('Wedding ticket is sealed')


def _ticket_source(db,owner,item,now):
    _valid_ticket(item,now)
    row=db.execute('''SELECT r.reservation FROM native_relationship_mail r
        JOIN player_mail_items i ON i.mail_id=r.mail_id
        WHERE i.item_uid=?AND r.recipient_uid=?AND i.claimed_uid=?AND i.claimed_at IS NOT NULL
        AND r.template=?''',(item['uid'],owner,owner,item['template'])).fetchone()
    if row is None:raise ValueError('Ticket has no current reservation producer')
    return row[0]


def owned_ticket(db,owner,reservation,template,*,ticket=0,now,items=None):
    """Personalized mail UID remains bound to its saved reservation/recipient."""
    from els_server.storage.relationship_mail import present as mail_present
    if not mail_present(db):raise ValueError('Wedding personalized ticket source missing')
    bound={r[0]for r in db.execute('''SELECT i.item_uid FROM native_relationship_mail r
        JOIN player_mail_items i ON i.mail_id=r.mail_id WHERE r.recipient_uid=?
        AND i.claimed_uid=?AND i.claimed_at IS NOT NULL AND r.reservation=?AND r.template=?''',
        (owner,owner,reservation,template))}
    for item in load_items(db,owner)if items is None else items:
        if item['template']!=template or item['uid']not in bound or ticket and item['uid']!=ticket:continue
        _valid_ticket(item,now)
        return item
    raise ValueError('Exact owned personalized wedding ticket required')


def ticket_information(db,owner,account,tickets,*,now):
    require_active_character(db,owner);require_owner(db,owner,account)
    inventory={item['uid']:item for item in load_items(db,owner)}
    from els_server.storage.relationship_mail import present as mail_present
    if tickets and not mail_present(db):raise ValueError('Wedding personalized source missing')
    result=[]
    for uid in tickets:
        item=inventory.get(uid)
        if item is None or item['template']not in(277151,277152,VOW_TICKET):
            raise ValueError('Wedding information requires owned personalized tickets')
        row=_record(db,_ticket_source(db,owner,item,now))
        result.append((uid,row))
    return result


def detail(db,owner,account,reservation,*,now):
    saved,_=pairing(db,owner,account)
    row=_record(db,reservation)
    if row['pair_id']!=saved['pair_id']:raise ValueError('Wedding detail belongs to another couple')
    owned_ticket(db,owner,reservation,spouse_ticket(row),now=now)
    guests=tuple(r[0]for r in db.execute('SELECT guest FROM native_wedding_invites WHERE reservation=?ORDER BY guest',(reservation,)))
    return row,guests


def lobby(db,page,*,now):
    #32B0410 initializes page1 and six rows; private passwords are never public.
    if type(page)is not int or page<1:raise ValueError('Wedding lobby page starts at1')
    if not present(db):return [],1
    condition='''finished_at IS NULL AND canceled_at IS NULL AND started_at IS NULL AND ends_at+60>?
        AND json_extract(ring_json,'$.template') NOT IN (277192,277193)
        AND EXISTS(SELECT 1 FROM native_couple_members_v1 g JOIN native_couple_members_v1 b
        ON b.pair_id=g.pair_id WHERE g.owner=native_wedding_bookings.groom
        AND b.owner=native_wedding_bookings.bride AND g.pair_id=native_wedding_bookings.pair_id)'''
    total=db.execute('SELECT COUNT(*)FROM native_wedding_bookings WHERE '+condition,(now,)).fetchone()[0]
    rows=[]
    for reservation, in db.execute('SELECT id FROM native_wedding_bookings WHERE '+condition+
                                   ' ORDER BY ends_at,id LIMIT 6 OFFSET ?',(now,(page-1)*6)):
        rows.append(dict(_record(db,reservation),password=''))
    return rows,max(1,(total+5)//6)


def invite(db,owner,account,request,payload,operation,*,now,guard,encode):
    """One blank invitation per newly invited guest, in the original writer."""
    from els_server.storage.inventory_actions import _identity,_previous,_commit
    from els_server.storage.equipment_receipt_state import current_changes
    if not db.in_transaction:raise ValueError('Wedding invitations require writer')
    guard(db);require_active_character(db,owner);require_owner(db,owner,account)
    owner,digest=_identity(owner,0x88e,payload,operation)
    saved,_=pairing(db,owner,account);row=_record(db,request['reservation'])
    if row['pair_id']!=saved['pair_id']:raise ValueError('Wedding invitation belongs to another couple')
    old=_previous(db,operation,digest);before=load_items(db,owner)
    if old is not None:
        answer=encode(current_changes(db,operation,owner,0x88e,old,before),True)
        for event in answer:encode_event(event)
        guard(db)
        return answer
    if row['started_at']is not None or row['finished_at']is not None or row['canceled_at']is not None or row['ends_at']+60<=now:
        raise ValueError('Wedding no longer accepts invitations')
    owned_ticket(db,owner,row['id'],277151,now=now)
    guests=request['guests']
    existing={r[0]for r in db.execute('SELECT guest FROM native_wedding_invites WHERE reservation=?',(row['id'],))}
    if not guests or len(existing)+len(guests)>100 or (existing|{row['groom'],row['bride']})&set(guests):
        raise ValueError('Wedding requires new guests within invitation capacity')
    for guest in guests:require_active_character(db,guest)
    sources=[];needed=len(guests)
    from els_server.domain.item_expiration import expired
    from els_server.domain.item_locks import locked
    for item in before:
        if item['template']!=277150 or item['group']!=4:continue
        if expired(item,now=now)or locked(item,now=now)or item.get('sealed',False):continue
        count=min(needed,item['count']);sources.append((item,count));needed-=count
        if not needed:break
    if needed:raise ValueError('Insufficient owned blank wedding invitations')
    for item,count in sources:
        if item['count']==count:remove(db,owner,item)
        elif db.execute('UPDATE inventory_items SET count=count-?WHERE owner=?AND uid=?AND count=?',
                        (count,owner,item['uid'],item['count'])).rowcount!=1:
            raise ValueError('Wedding invitation debit changed')
    db.executemany('INSERT INTO native_wedding_invites VALUES(?,?,?)',((row['id'],guest,now)for guest in guests))
    from els_server.storage.relationship_mail import invitation
    for guest in guests:invitation(db,row,guest,now)
    after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
    positions=[(item['group'],item['slot'])for item,count in sources]
    answer=encode([(position,current.get(position))for position in positions],False)
    for event in answer:encode_event(event)
    _commit(db,operation,digest,owner,0x88e,positions,before,after)
    guard(db)
    if load_items(db,owner)!=after or pairing(db,owner,account)[0]!=saved:
        raise ValueError('Wedding invitation source changed before commit')
    return answer


def reserve(db, owner, account, request, payload, operation, *, now, guard, issue, encode):
    """Issue is the server's fixed wedding-mail factory, never a request value."""
    if not db.in_transaction or type(now) is not int or now <= 0:
        raise ValueError('Wedding reservation writer/clock')
    if type(operation) is not str or not 1 <= len(operation) <= 160:
        raise ValueError('Wedding operation identity')
    guard(db)
    require_active_character(db,owner);require_owner(db,owner,account)
    saved,peer_account = pairing(db,owner,account)
    oath = request['hall'] == VOW_HALL
    if oath != (saved['kind'] in (7, 8)):
        raise ValueError('Reservation requires the corresponding relationship')
    peer = saved['peer_uid']
    if request['partner'] != peer:
        raise ValueError('Wedding request belongs to another couple')
    require_active_character(db,peer);require_owner(db,peer,peer_account)
    if present(db):
        old = db.execute('SELECT id,owner,account_id,request_hash FROM native_wedding_bookings '
                         'WHERE operation=?',(operation,)).fetchone()
        if old is not None:
            if old[1:] != (owner,account,_digest(owner,payload)):
                raise ValueError('Conflicting wedding reservation replay')
            row = _record(db,old[0])
            if row['pair_id'] != saved['pair_id']:
                raise ValueError('Wedding replay crosses couple generation')
            answer = encode(row,(),True)
            for event in answer:encode_event(event)
            guard(db)
            return answer
        if db.execute('SELECT 1 FROM native_wedding_bookings WHERE pair_id=? '
                      'AND finished_at IS NULL AND canceled_at IS NULL',
                      (saved['pair_id'],)).fetchone():
            raise ValueError('Wedding couple already has an unfinished reservation')
    start = request['ends_at']-86340
    day = datetime.fromtimestamp(start,CLIENT_ZONE).date()
    today = datetime.fromtimestamp(now,CLIENT_ZONE).date()
    if start % 3600 or not today <= day <= today+timedelta(days=6) or start+86400 <= now:
        raise ValueError('Wedding date outside original seven-day calendar')
    before = load_items(db,owner)
    ring = next((item for item in before if item['uid'] == request['ring']),None)
    allowed = (VOW_MARK,) if saved['kind']==7 else (REMINDER_MARK,) if saved['kind']==8 else (277141,277142)
    if ring is None or (ring['group'],ring['metadata']) != (4,0) or ring['template'] not in allowed:
        raise ValueError('Wedding requires the exact owned current ring')
    require_current(ring,now=now);require_unlocked(ring,now=now)
    if ring.get('sealed',False):
        raise ValueError('Wedding ring is sealed')
    if ring['template'] == 277141 and married_since(db,saved['pair_id']) is None:
        raise ValueError('Remind ring requires an existing marriage')
    guests = request['guests']
    if oath and (guests or request['reserved_seats'] or request['officiant'] or request['message'] or request['password']):
        raise ValueError('Vow reservations have no guests or wedding options')
    if {owner,peer} & set(guests):
        raise ValueError('Wedding couple is not a guest')
    for guest in guests:require_active_character(db,guest)
    types = dict(db.execute('SELECT uid,unit_type FROM characters WHERE uid IN(?,?)',(owner,peer)))
    owner_is_groom = types[owner] in MALE or types[owner] == 10 and types[peer] in FEMALE
    groom,bride = (owner,peer) if oath or owner_is_groom else (peer,owner)
    initialize(db)
    reservation = db.execute('''INSERT INTO native_wedding_bookings(
        pair_id,owner,account_id,groom,bride,hall,officiant,ends_at,message,password,public,
        reserved_seats,created_at,ring_json,operation,request_hash,payload)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (saved['pair_id'],owner,account,groom,bride,2 if oath else request['hall'],request['officiant'],request['ends_at'],
         request['message'],request['password'],False if oath else request['public'],request['reserved_seats'],now,
         _json(ring),operation,_digest(owner,payload),payload)).lastrowid
    if not 0 < reservation < 2**31:
        raise ValueError('Native wedding reservation ID bound')
    db.executemany('INSERT INTO native_wedding_invites VALUES(?,?,?)',
                   ((reservation,guest,now) for guest in guests))
    if ring['count'] == 1:
        remove(db,owner,ring)
    elif db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=?AND uid=?AND count=?',
                    (owner,ring['uid'],ring['count'])).rowcount != 1:
        raise ValueError('Wedding bound ring debit changed')
    after = load_items(db,owner)
    row = _record(db,reservation)
    issue(db,row,ring,now)
    # Ring contents are sent as real mail; reservation ACK reports only debit.
    position = (ring['group'],ring['slot'])
    replacement = next((i for i in after if (i['group'],i['slot']) == position),None)
    answer = encode(row,((position,replacement),),False)
    for event in answer:encode_event(event)
    guard(db)
    present(db)
    if load_items(db,owner) != after or pairing(db,owner,account) != (saved,peer_account):
        raise ValueError('Wedding source changed before commit')
    return answer


def spouse_ticket(row):
    return VOW_TICKET if row['hall'] == VOW_HALL else 277151
