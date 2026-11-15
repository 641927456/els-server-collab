"""Account achievement records, server-source deduplication and character displays."""
from datetime import datetime,timedelta,timezone
import hashlib,json
from els_server.domain.achievement_catalog import achievement
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character


class AchievementError(ValueError):
    def __init__(self,message,code):super().__init__(message);self.code=code


def ensure(db):
    from els_server.storage.achievement_history import ensure_indexes
    ensure_indexes(db)
    db.execute('''CREATE TABLE IF NOT EXISTS native_achievement_progress(
        account_id INTEGER NOT NULL,achievement INTEGER NOT NULL,condition INTEGER NOT NULL,
        value INTEGER NOT NULL CHECK(value BETWEEN 0 AND 2147483647),
        complete INTEGER NOT NULL CHECK(complete IN(0,1)),
        PRIMARY KEY(account_id,achievement,condition))''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_achievement_completed(
        account_id INTEGER NOT NULL,achievement INTEGER NOT NULL,completed_at INTEGER NOT NULL,
        received_at INTEGER NOT NULL DEFAULT 0,recipient_uid INTEGER,mail_id INTEGER,
        PRIMARY KEY(account_id,achievement))''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_achievement_displays(
        owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
        slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 2),achievement INTEGER NOT NULL,
        PRIMARY KEY(owner,slot),UNIQUE(owner,achievement))''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_achievement_operations(
        operation TEXT PRIMARY KEY NOT NULL,account_id INTEGER NOT NULL,owner INTEGER NOT NULL,
        kind TEXT NOT NULL,digest TEXT NOT NULL,result_json TEXT NOT NULL)''')


def exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='native_achievement_completed'").fetchone()is not None


def _actor(db,account,owner):
    if not db.in_transaction:raise ValueError('Achievement mutation requires its business transaction')
    require_owner(db,owner,account);require_active_character(db,owner)


def _operation(db,account,owner,kind,payload,operation):
    if type(operation)is not str or not operation:raise ValueError('Achievement source identity required')
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    old=db.execute('SELECT account_id,owner,kind,digest,result_json FROM native_achievement_operations WHERE operation=?',(operation,)).fetchone()
    if old is None:return digest,None
    if old[:4]!=(account,owner,kind,digest):raise ValueError('Achievement operation conflicts with its server source')
    return digest,json.loads(old[4])


def _save(db,account,owner,kind,digest,operation,result):
    db.execute('INSERT INTO native_achievement_operations VALUES(?,?,?,?,?,?)',
        (operation,account,owner,kind,digest,json.dumps(result,sort_keys=True,separators=(',',':'))))


def record(db,account,owner,updates,operation,now):
    """Consume condition results from a server business producer in that same SQL transaction.

    No native packet supplies updates. In particular,6C3 debug completion is
    excluded from the ordinary request dispatcher.
    """
    _actor(db,account,owner)
    for row in updates:
        definition=achievement(row['achievement'])
        if row['condition']not in {c['id']for c in definition['conditions']}:
            raise ValueError('Condition does not belong to this achievement')
        if type(row['value'])is not int or not 0<=row['value']<=2**31-1 or type(row['complete'])is not bool:
            raise ValueError('Invalid server achievement condition result')
    ensure(db);digest,old=_operation(db,account,owner,'server-progress',updates,operation)
    if old is not None:return dict(old,replayed=True)
    affected=set()
    for row in updates:
        db.execute('INSERT INTO native_achievement_progress VALUES(?,?,?,?,?) ON CONFLICT(account_id,achievement,condition) '
            'DO UPDATE SET value=excluded.value,complete=excluded.complete',
            (account,row['achievement'],row['condition'],row['value'],int(row['complete'])))
        affected.add(row['achievement'])
    completed=[]
    for identity in sorted(affected):
        conditions={row[0]:bool(row[1])for row in db.execute('SELECT condition,complete FROM native_achievement_progress WHERE account_id=?AND achievement=?',(account,identity))}
        if all(conditions.get(c['id'],False)for c in achievement(identity)['conditions']):
            fresh=db.execute('INSERT INTO native_achievement_completed(account_id,achievement,completed_at) VALUES(?,?,?) '
                'ON CONFLICT(account_id,achievement) DO NOTHING',(account,identity,now)).rowcount
            if fresh:completed.append(identity)
    result=dict(completed=completed,replayed=False)
    _save(db,account,owner,'server-progress',digest,operation,result)
    return result


def watched(db,owner):
    if not exists(db):return []
    return [row[0]for row in db.execute('SELECT achievement FROM native_achievement_displays WHERE owner=?ORDER BY slot',(owner,))]


def statuses(db,account,owners):
    """Read common Unit fields once for an already scoped character snapshot."""
    from els_server.domain.achievement_catalog import points
    owners=tuple(owners)
    if not owners:return {}
    result={owner:dict(points=[0,0,0,0],watched=[],state_flag=False)for owner in owners}
    if not exists(db):return result
    scores=points([dict(id=row[0])for row in db.execute(
        'SELECT achievement FROM native_achievement_completed WHERE account_id=?',(account,))])
    for value in result.values():value['points']=scores
    for owner,identity in db.execute('SELECT owner,achievement FROM native_achievement_displays WHERE owner IN('
            +','.join('?'for _ in owners)+') ORDER BY owner,slot',owners):
        result[owner]['watched'].append(identity)
    return result


def toggle_display(db,account,owner,identity,operation):
    _actor(db,account,owner);achievement(identity);ensure(db)
    digest,old=_operation(db,account,owner,'display',identity,operation)
    if old is not None:return watched(db,owner)
    if not db.execute('SELECT 1 FROM native_achievement_completed WHERE account_id=?AND achievement=?',(account,identity)).fetchone():
        raise AchievementError('Only completed achievements may be displayed',1890)
    old=db.execute('SELECT slot FROM native_achievement_displays WHERE owner=?AND achievement=?',(owner,identity)).fetchone()
    if old is not None:
        db.execute('DELETE FROM native_achievement_displays WHERE owner=?AND achievement=?',(owner,identity))
    else:
        occupied={row[0]for row in db.execute('SELECT slot FROM native_achievement_displays WHERE owner=?',(owner,))}
        if len(occupied)==3:raise AchievementError('Achievement display list is full',2662)
        slot=next(slot for slot in range(3)if slot not in occupied)
        db.execute('INSERT INTO native_achievement_displays VALUES(?,?,?)',(owner,slot,identity))
    result=watched(db,owner);_save(db,account,owner,'display',digest,operation,result)
    return result


def snapshot(db,account,owner):
    require_owner(db,owner,account)
    if not exists(db):return dict(progress=[],completed=[],watched=[])
    progress={}
    for ident,cid,count,complete in db.execute('SELECT achievement,condition,value,complete FROM native_achievement_progress WHERE account_id=?ORDER BY achievement,condition',(account,)):
        progress.setdefault(ident,dict(id=ident,conditions=[]))['conditions'].append(dict(id=cid,count=count,complete=bool(complete)))
    zone=timezone(timedelta(hours=8))
    completed=[dict(id=ident,completed_at=datetime.fromtimestamp(stamp,zone).strftime('%Y-%m-%d %H:%M:%S'),received=bool(received))
        for ident,stamp,received in db.execute('SELECT achievement,completed_at,received_at FROM native_achievement_completed WHERE account_id=?ORDER BY achievement',(account,))]
    return dict(progress=list(progress.values()),completed=completed,watched=watched(db,owner))


def recipient(db,mail_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='native_achievement_mail'").fetchone():return None
    row=db.execute('SELECT owner FROM native_achievement_mail WHERE mail_id=?',(mail_id,)).fetchone()
    return None if row is None else row[0]


def claim(db,account,owner,identity,now):
    """Click-to-current-character mail; unresolved groups retain their claim."""
    from els_server.domain.achievement_catalog import reward_items
    _actor(db,account,owner);definition=achievement(identity)
    row=db.execute('SELECT received_at FROM native_achievement_completed WHERE account_id=?AND achievement=?',
        (account,identity)).fetchone()if exists(db)else None
    if row is None:raise AchievementError('Achievement is not completed',1893)
    if row[0]:return []
    items=reward_items(identity)
    if items is None:raise AchievementError('Original achievement reward is pending verification',2005)
    from els_server.storage.game_mail import ensure as ensure_mail
    from els_server.storage.player_mail import ORDINARY_RETENTION,decorate
    from els_server.storage.mail_attachments import put
    from els_server.storage.item_instances import next_uid
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,validate_item,item_body
    from els_server.protocol.mail_attachment_messages import header,detail
    ensure_mail(db)
    db.execute('''CREATE TABLE IF NOT EXISTS native_achievement_mail(
        account_id INTEGER NOT NULL,achievement INTEGER NOT NULL,
        owner INTEGER NOT NULL REFERENCES characters(uid),ordinal INTEGER NOT NULL,
        mail_id INTEGER PRIMARY KEY REFERENCES game_mail(id),
        UNIQUE(account_id,achievement,ordinal))''')
    mails=[]
    for reward in items:
        template=reward['template'];remaining=reward['count']
        while remaining:
            count=min(remaining,TEMPLATE_MAX_STACKS[template]);ordinal=len(mails)
            mid=db.execute('''INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at)
                VALUES(?,?,?,?,?,0,?,?)''',(f'achievement-{identity}-{ordinal}',account,'阿莉尔',
                definition['name'],'业绩已达成，请领取奖励。',now,now+ORDINARY_RETENTION)).lastrowid
            db.execute('INSERT INTO native_achievement_mail VALUES(?,?,?,?,?)',(account,identity,owner,ordinal,mid))
            item=validate_item(dict(uid=next_uid(db),template=template,metadata=VERIFIED_TEMPLATES[template],
                group=TEMPLATE_BAG_GROUPS[template],slot=0,count=count))
            item_body(item);put(db,mid,item,item)
            cur=db.execute('SELECT *FROM game_mail WHERE id=?',(mid,))
            letter=decorate(db,dict(zip((c[0]for c in cur.description),cur.fetchone())),now=now)
            header(letter);detail(letter)
            mails.append(mid);remaining-=count
    db.execute('UPDATE native_achievement_completed SET received_at=?,recipient_uid=?,mail_id=? '
        'WHERE account_id=?AND achievement=?',(now,owner,mails[0]if mails else None,account,identity))
    return mails
