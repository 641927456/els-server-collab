"""One bilateral mentor relation per character, with atomic removal/graduation."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib,json,sqlite3,time
from els_server.storage.friend_state import exists,character,profile
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character

MIN_RELATION_SECONDS = 48 * 3600


class MentorError(ValueError):
    def __init__(self, message, code=1977):
        super().__init__(message)
        self.code = code


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS native_mentor_relations(
        owner INTEGER PRIMARY KEY REFERENCES characters(uid) ON DELETE CASCADE,
        partner INTEGER NOT NULL UNIQUE REFERENCES characters(uid) ON DELETE CASCADE,
        is_student INTEGER NOT NULL CHECK(is_student IN(0,1)), generation TEXT NOT NULL,
        formed_at INTEGER NOT NULL, CHECK(owner<>partner))''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_mentor_operations(
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
        kind INTEGER NOT NULL,digest TEXT NOT NULL,result_json TEXT NOT NULL,state_json TEXT NOT NULL)''')


def relation(db, owner):
    if not exists(db, 'native_mentor_relations'):
        return None
    row = db.execute('SELECT partner,is_student,generation,formed_at FROM native_mentor_relations WHERE owner=?',
                     (owner,)).fetchone()
    if row is None:
        return None
    other, student, generation, formed = row
    if db.execute('SELECT partner,is_student,generation,formed_at FROM native_mentor_relations WHERE owner=?',
                  (other,)).fetchone() != (owner, 1-student, generation, formed):
        raise MentorError('Mentor relation is not bilateral')
    return dict(owner=owner,partner=other,is_student=bool(student),generation=generation,formed_at=formed)


def account_has_student(db, account):
    return exists(db, 'native_mentor_relations') and db.execute(
        'SELECT 1 FROM native_mentor_relations m JOIN character_owners o ON o.uid=m.owner '
        'WHERE o.account_id=? AND m.is_student=1 LIMIT 1', (account,)).fetchone() is not None


def account_has_99(db, account):
    from els_server.storage.character_lifecycle import visible_ids
    return any(db.execute('SELECT level FROM characters WHERE uid=?', (uid,)).fetchone() == (99,)
               for uid in visible_ids(db, account))


def qualified_teacher(db, owner, account):
    from els_server.domain.character_rules import CLASSES
    row = character(db, uid=owner)
    if row['account_id'] != account or CLASSES[row['unit_class']]['stage'] < 2:
        return False
    if not account_has_99(db, account) or account_has_student(db, account):
        return False
    from els_server.storage.mentor45000_scope import _integrity, _carriers
    bound = _integrity(db, owner)
    return bound is not None and _carriers(db, owner) == [('done', bound[0])]


def role(db, owner, account):
    require_owner(db, owner, account)
    saved = relation(db, owner)
    if saved is not None:
        return int(saved['is_student'])
    if qualified_teacher(db, owner, account):
        return 0
    return 2 if account_has_99(db, account) else 1


def public_info(db, owner, live, *, saved=None, is_student=None):
    row = character(db, uid=owner)
    value = profile(db, row, 0, 0, live)
    if saved is not None:
        if owner not in (saved['owner'], saved['partner']):
            raise MentorError('Public mentor record is outside this relation')
        is_student = saved['is_student'] if owner == saved['owner'] else not saved['is_student']
    if type(is_student) is not bool:
        raise MentorError('Public mentor record requires an authoritative role')
    until = '' if saved is None else datetime.fromtimestamp(
        saved['formed_at']+MIN_RELATION_SECONDS, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    return dict(uid=owner,level=row['level'],name=row['name'],online=live is not None,unlock_at=until,
                rank=value['rank'],is_student=is_student,unit_class=row['unit_class'])


def require_pair_eligibility(db, teacher, student):
    my, other = character(db, uid=teacher), character(db, uid=student)
    if teacher == student or my['account_id'] == other['account_id']:
        raise MentorError('Mentor participants require different accounts')
    for uid in (teacher, student):
        require_active_character(db, uid)
        if relation(db, uid) is not None:
            raise MentorError('Participant already has a mentor relation')
    if not qualified_teacher(db, teacher, my['account_id']):
        raise MentorError('Teacher qualification is incomplete', 1957)
    if account_has_99(db, other['account_id']):
        raise MentorError('Student account already has a level99 character')
    return my, other


def _state(db, owners):
    return json.dumps([relation(db, uid) for uid in owners], sort_keys=True, separators=(',', ':'))


def recipient(db, mail_id):
    if not exists(db, 'native_mentor_graduations'):
        return None
    row = db.execute('SELECT student FROM native_mentor_graduations WHERE mail_id=?', (mail_id,)).fetchone()
    return None if row is None else row[0]


def _graduate(db, saved, now):
    teacher = saved['partner'] if saved['is_student'] else saved['owner']
    student = saved['owner'] if saved['is_student'] else saved['partner']
    require_active_character(db, student)
    from els_server.storage.game_mail import ensure as ensure_mail
    ensure_mail(db)
    db.execute('''CREATE TABLE IF NOT EXISTS native_mentor_graduations(
        generation TEXT PRIMARY KEY,student INTEGER NOT NULL REFERENCES characters(uid),
        teacher INTEGER NOT NULL REFERENCES characters(uid),mail_id INTEGER NOT NULL UNIQUE REFERENCES game_mail(id))''')
    if db.execute('SELECT 1 FROM native_mentor_graduations WHERE generation=?', (saved['generation'],)).fetchone():
        raise MentorError('This relation already graduated')
    account = character(db, uid=student)['account_id']
    from els_server.storage.player_mail import ORDINARY_RETENTION
    campaign = 'mentor-graduate-'+hashlib.sha256(saved['generation'].encode()).hexdigest()
    mid = db.execute('INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at) '
        'VALUES(?,?,?,?,?,0,?,?)', (campaign,account,'阿莉尔','出师的证明','恭喜达到99级并完成出师，请领取称号奖励。',
                                  now,now+ORDINARY_RETENTION)).lastrowid
    db.execute('INSERT INTO native_mentor_graduations VALUES(?,?,?,?)', (saved['generation'],student,teacher,mid))
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item,item_body
    from els_server.domain.acquisition_policy import require_acquirable
    from els_server.storage.item_instances import next_uid
    from els_server.storage.mail_attachments import put
    require_acquirable(189801)
    item = validate_item(dict(uid=next_uid(db),template=189801,metadata=VERIFIED_TEMPLATES[189801],
                              group=TEMPLATE_BAG_GROUPS[189801],slot=0,count=1))
    item_body(item)
    put(db,mid,item,item)
    from els_server.storage.player_mail import decorate
    from els_server.protocol.mail_attachment_messages import header,detail
    cursor = db.execute('SELECT * FROM game_mail WHERE id=?', (mid,))
    row = dict(zip((column[0] for column in cursor.description),cursor.fetchone()))
    row = decorate(db,row,now=now)
    header(row)
    detail(row)
    return mid


def perform(path, owner, account, kind, payload, operation, guard, encode, *, invitation=None, now=None):
    if kind not in (0x1e4, 0x1eb) or type(operation) is not str or not 1 <= len(operation) <= 160:
        raise MentorError('Mentor operation identity')
    now = int(time.time()) if now is None else now
    digest = hashlib.sha256(str(account).encode()+b':'+str(kind).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        guard(db)
        require_owner(db,owner,account)
        require_active_character(db,owner)
        ensure(db)
        old = db.execute('SELECT owner,kind,digest,result_json,state_json FROM native_mentor_operations '
                         'WHERE operation=?', (operation,)).fetchone()
        if old is not None:
            if old[:3] != (owner,kind,digest):
                raise MentorError('Conflicting mentor replay')
            result = json.loads(old[3])
            if _state(db,result['owners']) != old[4]:
                raise MentorError('Mentor state changed after the original operation')
            response = encode(db,result,True)
            guard(db)
            return response
        if kind == 0x1eb:
            if invitation is None:
                raise MentorError('A current accepted invitation is required')
            teacher, student = invitation['teacher'], invitation['student']
            if owner != invitation['recipient'] or owner not in (teacher,student):
                raise MentorError('Mentor invitation recipient changed')
            require_pair_eligibility(db,teacher,student)
            generation = invitation['generation']
            db.executemany('INSERT INTO native_mentor_relations VALUES(?,?,?,?,?)',
                ((teacher,student,0,generation,now),(student,teacher,1,generation,now)))
            result = dict(owners=[teacher,student],generation=generation,action='accepted',mail_id=None)
        else:
            target = int.from_bytes(payload,'big')
            saved = relation(db,owner)
            if saved is None or saved['partner'] != target:
                raise MentorError('Current partner is required', 1981)
            student = owner if saved['is_student'] else target
            graduated = character(db,uid=student)['level'] == 99
            if now < saved['formed_at']+MIN_RELATION_SECONDS:
                raise MentorError('Mentor relation has not reached48hours', 1974)
            mid = _graduate(db,saved,now) if graduated else None
            owners = sorted((owner,target))
            db.execute('DELETE FROM native_mentor_relations WHERE generation=? AND owner IN(?,?)',
                       (saved['generation'],owner,target))
            result = dict(owners=owners,generation=saved['generation'],action='graduated' if graduated else 'removed',mail_id=mid)
        response = encode(db,result,False)
        guard(db)
        db.execute('INSERT INTO native_mentor_operations VALUES(?,?,?,?,?,?)',
            (operation,owner,kind,digest,json.dumps(result,sort_keys=True),_state(db,result['owners'])))
        return response


def retire_deleted_character(db, owner):
    """Finalized tombstones retain their data but no longer retain a social slot."""
    if not db.in_transaction:
        raise MentorError('Character finalization requires its existing transaction')
    saved = relation(db,owner)
    if saved is not None:
        db.execute('DELETE FROM native_mentor_relations WHERE generation=? AND owner IN(?,?)',
                   (saved['generation'],owner,saved['partner']))


def search(path,owner,account,operation,guard,encode,*,now=None):
    """The native60s character cooldown survives reconnects; a replay never broadcasts twice."""
    now=int(time.time())if now is None else now
    digest=hashlib.sha256(f'{account}:{0x714}:'.encode()).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_owner(db,owner,account);require_active_character(db,owner)
        ensure(db)
        db.execute('''CREATE TABLE IF NOT EXISTS native_mentor_search_times(
            owner INTEGER PRIMARY KEY REFERENCES characters(uid) ON DELETE CASCADE,next_at INTEGER NOT NULL)''')
        old=db.execute('SELECT owner,kind,digest,result_json,state_json FROM native_mentor_operations WHERE operation=?',
                       (operation,)).fetchone()
        saved=db.execute('SELECT next_at FROM native_mentor_search_times WHERE owner=?',(owner,)).fetchone()
        state=lambda:json.dumps(dict(next_at=saved[0]if saved else None,relation=relation(db,owner)),sort_keys=True)
        if old is not None:
            if old[:3]!=(owner,0x714,digest)or old[4]!=state():raise MentorError('Conflicting or retired mentor search replay')
            response=encode(db,json.loads(old[3]),True);guard(db);return response
        if relation(db,owner)is not None or account_has_99(db,account):
            raise MentorError('Only an unbound student can search for a teacher',1958)
        if saved is not None and saved[0]>now:raise MentorError('Mentor search cooldown',1959)
        result=dict(owner=owner,next_at=now+60)
        db.execute('INSERT INTO native_mentor_search_times VALUES(?,?) '
                   'ON CONFLICT(owner) DO UPDATE SET next_at=excluded.next_at',(owner,now+60))
        saved=(now+60,)
        response=encode(db,result,False);guard(db)
        db.execute('INSERT INTO native_mentor_operations VALUES(?,?,?,?,?,?)',
            (operation,owner,0x714,digest,json.dumps(result,sort_keys=True),state()))
        return response
