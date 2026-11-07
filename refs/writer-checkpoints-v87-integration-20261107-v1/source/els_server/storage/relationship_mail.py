"""Character-owned relationship letters, through the shared attachment escrow."""
from calendar import monthrange
from contextlib import closing
from datetime import datetime,time as daytime,timedelta
import hashlib,json,sqlite3,time

from els_server.domain.item_expiration import CLIENT_ZONE
from els_server.storage import relationships,weddings

TABLE='native_relationship_mail'
SCHEMA='''CREATE TABLE native_relationship_mail(
    source TEXT PRIMARY KEY,mail_id INTEGER NOT NULL UNIQUE REFERENCES game_mail(id),
    recipient_uid INTEGER NOT NULL REFERENCES characters(uid),pair_id TEXT NOT NULL,
    reservation INTEGER,
    mail_type INTEGER NOT NULL CHECK(mail_type IN(22,23,24)),
    template INTEGER NOT NULL,created_at INTEGER NOT NULL)'''


def present(db):
    row=db.execute("SELECT sql FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()
    if row is not None and row[0]!=SCHEMA:raise ValueError('Unknown relationship mail schema')
    return row is not None


def metadata(db,mail_id):
    if not present(db):return None
    row=db.execute('SELECT recipient_uid,mail_type FROM native_relationship_mail WHERE mail_id=?',(mail_id,)).fetchone()
    return None if row is None else tuple(row)


def _months(value,delta):
    month=value.year*12+value.month-1+delta;year,m=divmod(month,12);m+=1
    return value.replace(year=year,month=m,day=min(value.day,monthrange(year,m)[1]))


def _put(db,source,owner,pair,template,*,created_at,expires_at,mail_type,title,body,reservation=None,quantity=1):
    if not db.in_transaction:raise ValueError('Relationship mail requires original writer')
    from els_server.storage.game_mail import ensure
    ensure(db)
    if not present(db):db.execute(SCHEMA)
    old=db.execute('SELECT mail_id,recipient_uid,pair_id,reservation,mail_type,template,created_at '
                   'FROM native_relationship_mail WHERE source=?',(source,)).fetchone()
    if old is not None:
        if tuple(old)[1:]!=(owner,pair,reservation,mail_type,template,created_at):
            raise ValueError('Conflicting relationship mail source')
        return None
    account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
    if account is None:raise ValueError('Relationship mail saved recipient missing')
    mid=db.execute('''INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at)
        VALUES(?,?,?,?,?,0,?,?)''',('relationship-'+hashlib.sha256(source.encode()).hexdigest(),
                                 account[0],'阿莉尔',title,body,created_at,expires_at)).lastrowid
    db.execute('INSERT INTO native_relationship_mail VALUES(?,?,?,?,?,?,?,?)',
               (source,mid,owner,pair,reservation,mail_type,template,created_at))
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item,item_body
    from els_server.storage.item_instances import next_uid
    from els_server.storage.mail_attachments import put
    item=validate_item(dict(uid=next_uid(db),template=template,metadata=VERIFIED_TEMPLATES[template],
                           group=TEMPLATE_BAG_GROUPS[template],slot=0,count=quantity))
    item_body(item);put(db,mid,item,item)
    from els_server.storage.player_mail import decorate
    from els_server.protocol.mail_attachment_messages import header,detail
    cursor=db.execute('SELECT *FROM game_mail WHERE id=?',(mid,))
    mail=dict(zip((c[0]for c in cursor.description),cursor.fetchone()))
    mail=decorate(db,mail,now=created_at);header(mail);detail(mail)
    return mid


def reservation(db,row,ring,now):
    """Approved both-spouse parcel and30 blank invitations for the proposer."""
    stored=weddings._record(db,row['id'])
    if stored!=row or json.loads(stored['ring_json'])!=ring:
        raise ValueError('Reservation mail lost exact ring/booking source')
    saved,_=weddings.pairing(db,row['owner'],row['account_id'])
    if saved['pair_id']!=row['pair_id']or row['created_at']!=now:
        raise ValueError('Reservation mail changed couple generation/clock')
    from els_server.storage.player_mail import ORDINARY_RETENTION
    from els_server.game_data import client_data
    for recipient,is_groom in((row['groom'],True),(row['bride'],False)):
        robe=(277144 if is_groom else 277146)if ring['template']==277142 else(277143 if is_groom else 277145)
        for template in(robe,277147,277151):
            _put(db,f'wedding:{row["id"]}:{recipient}:{template}',recipient,row['pair_id'],template,
                 created_at=now,expires_at=now+ORDINARY_RETENTION,mail_type=24,reservation=row['id'],
                 title=client_data().item(template)['name'],body='你们的婚礼已经预约，请领取预约券及礼品。')
    _put(db,f'wedding:{row["id"]}:{row["owner"]}:277150',row['owner'],row['pair_id'],277150,quantity=30,
         created_at=now,expires_at=now+ORDINARY_RETENTION,mail_type=24,reservation=row['id'],
         title='婚礼邀请函',body='你可以用这些空白邀请函追加邀请嘉宾。')
    for guest, in db.execute('SELECT guest FROM native_wedding_invites WHERE reservation=?ORDER BY guest',(row['id'],)):
        invitation(db,row,guest,now)


def invitation(db,row,guest,now):
    if db.execute('SELECT 1 FROM native_wedding_invites WHERE reservation=?AND guest=?',(row['id'],guest)).fetchone()is None:
        raise ValueError('Wedding invitation mail lacks saved entitlement')
    from els_server.storage.player_mail import ORDINARY_RETENTION
    return _put(db,f'wedding:{row["id"]}:{guest}:277152',guest,row['pair_id'],277152,
                created_at=now,expires_at=now+ORDINARY_RETENTION,mail_type=23,reservation=row['id'],
                title='婚礼请帖',body=f'{row["groom_name"]}与{row["bride_name"]}邀请你参加婚礼。')


def ceremony(db,row,roster,now):
    from els_server.storage.wedding_ceremonies import present as ceremony_present
    if not ceremony_present(db)or row['finished_at']!=now:
        raise ValueError('Wedding participation reward lacks marriage commit')
    saved=db.execute('SELECT pair_id,at,mode,roster_json FROM native_wedding_ceremonies WHERE reservation=?',(row['id'],)).fetchone()
    if saved!=(row['pair_id'],now,'ceremony',weddings._json(roster)):
        raise ValueError('Wedding reward roster differs from mutual ceremony')
    from els_server.storage.player_mail import ORDINARY_RETENTION
    for person in roster:
        spouse=person['role']in(1,2);template=277153 if spouse else 277155
        _put(db,f'wedding-complete:{row["id"]}:{person["uid"]}:{template}',person['uid'],row['pair_id'],template,
             quantity=1 if spouse else 20,created_at=now,expires_at=now+ORDINARY_RETENTION,
             mail_type=22,reservation=row['id'],title='婚礼祝贺宝箱'if spouse else'婚礼嘉宾礼物',
             body='感谢你参加本次婚礼，请领取婚礼奖励。')


def anniversary(db,owner,account,*,now):
    """Materialize unexpired earned weeks; creation day never grants a cube.

    Each letter retains its original due date and three-calendar-month expiry.
    Reconnects, reminder ceremonies and receipt deletion cannot mint it again.
    """
    if not db.in_transaction:raise ValueError('Anniversary requires writer')
    from els_server.storage.item_actor import require_active_character
    require_active_character(db,owner)
    saved=relationships.snapshot(db,owner,account)
    if saved is None:return []
    married=weddings.married_since(db,saved['pair_id'])
    base=saved['created_at']if married is None else married['married_at']
    template=160762 if married is None else 277154
    origin=datetime.fromtimestamp(base,CLIENT_ZONE).date()
    today=datetime.fromtimestamp(now,CLIENT_ZONE)
    weeks=(today.date()-origin).days//7
    if weeks<1:return []
    oldest=_months(today,-3).date()
    first=max(1,(oldest-origin).days//7)
    result=[]
    for week in range(first,weeks+1):
        due=datetime.combine(origin+timedelta(days=week*7),daytime(),CLIENT_ZONE)
        expiry=int(_months(due,3).timestamp())
        if expiry<=now:continue
        source=f'anniversary:{saved["pair_id"]}:{owner}:{template}:{week}'
        title='情侣纪念日宝箱'if married is None else'结婚纪念日宝箱'
        mid=_put(db,source,owner,saved['pair_id'],template,created_at=int(due.timestamp()),
                 expires_at=expiry,mail_type=22,title=title,body='这是你们本周纪念日的礼物，请及时领取。')
        if mid is not None:result.append(mid)
    return result


def maintenance(path,account,owner,*,now=None):
    # Most mailbox polls have no relationship to settle. Validate that case
    # in a read snapshot instead of reserving SQLite's sole writer. A real
    # relationship still follows the original transaction and fresh checks.
    from els_server.storage.read_scope import snapshot_connection
    from els_server.storage.item_actor import require_active_character
    with snapshot_connection(path,timeout=.1)as db:
        db.execute('BEGIN')
        require_active_character(db,owner)
        if relationships.snapshot(db,owner,account)is None:return []
    with closing(sqlite3.connect(path,timeout=.1))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        return anniversary(db,owner,account,now=int(time.time())if now is None else now)
