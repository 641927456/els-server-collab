"""Character-owned references to existing pages, never copied ownership."""
from contextlib import closing
from pathlib import Path
import json,sqlite3,hashlib
from els_server.protocol import character_preset_messages as wire
from els_server.protocol.protocol_codec import encode_event

TABLE='character_presets_v1'
RECEIPTS='character_preset_receipts_v1'
CAPACITY='character_preset_capacity_v1'


def exists(db,table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(table,)).fetchone()is not None


def defaults(count=2):
    return [dict(page=i,name='',equipment=1,skills=1,resonance=0,guild=0,custom=0,synergy=1)for i in range(1,count+1)]


def page_count(db,owner):
    row=db.execute('SELECT opened FROM character_preset_capacity_v1 WHERE owner=?',(owner,)).fetchone()if exists(db,CAPACITY)else None
    count=2 if row is None else row[0]
    if type(count)is not int or not 2<=count<=4:raise ValueError('Preset opened page count')
    return count


def ensure_records(db):
    # Widen the exact earlier two-page schema atomically; preserve its rows.
    old=db.execute("SELECT sql FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()
    if old and 'CHECK(page BETWEEN 1 AND 2)'in old[0]:
        db.execute('CREATE TABLE character_presets_wide(owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,page INTEGER NOT NULL CHECK(page BETWEEN 1 AND 4),document TEXT NOT NULL,PRIMARY KEY(owner,page))')
        db.execute('INSERT INTO character_presets_wide SELECT owner,page,document FROM character_presets_v1')
        db.execute('DROP TABLE character_presets_v1')
        db.execute('ALTER TABLE character_presets_wide RENAME TO character_presets_v1')
    else:
        db.execute('CREATE TABLE IF NOT EXISTS character_presets_v1(owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,page INTEGER NOT NULL CHECK(page BETWEEN 1 AND 4),document TEXT NOT NULL,PRIMARY KEY(owner,page))')


def snapshot(db,owner):
    pages=defaults(page_count(db,owner))
    account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()[0]
    from els_server.storage.ordinary_skill_pages import meta
    selected=dict(skills=meta(db,owner)['selected'])
    if exists(db,'resonance2026_characters'):
        from els_server.domain.resonance_allocation_flow import profiles
        state=profiles(db).pages.read(account,owner)
        if state is not None and state.enabled:selected['resonance']=state.selected_page
    from els_server.storage.guild_membership_state import snapshot as membership
    guild=membership(db,owner,account)
    if guild is not None:
        from els_server.storage.guild_system_state import member
        selected['guild']=member(guild['system'],owner).get('page',1)
    for page in pages:page.update(selected)
    if not exists(db,TABLE):return pages
    saved=db.execute('SELECT page,document FROM character_presets_v1 WHERE owner=? ORDER BY page',(owner,)).fetchall()
    for page,raw in saved:
        value=json.loads(raw)
        if value['page']!=page or not 1<=page<=len(pages):raise ValueError('Preset saved page ownership')
        wire.record(value);pages[page-1]=value
    return pages


def owned_pages(db,owner,account):
    from els_server.storage.ordinary_skill_pages import meta
    skills=set(range(1,meta(db,owner)['count']+1))
    resonance={0}
    if exists(db,'resonance2026_characters'):
        from els_server.domain.resonance_allocation_flow import profiles
        state=profiles(db).pages.read(account,owner)
        if state is not None and state.enabled:resonance=set(p.page_id for p in state.pages)
    guild={0}
    from els_server.storage.guild_membership_state import snapshot as membership
    saved=membership(db,owner,account)
    if saved is not None:
        guild={int(k)for k in saved['system']['pages']}
    # Existing server has one equipment page, one custom configuration, and
    # the original free synergy page. Extra pages require their own authority.
    return dict(equipment={1},skills=skills,resonance=resonance,guild=guild,custom={0},synergy={1})


def save(path,owner,account,payload,operation,guard):
    value=wire.request(payload)
    if type(operation)is not str or not 1<=len(operation)<=160:raise ValueError('Preset operation')
    digest=hashlib.sha256(str(account).encode()+b':'+payload).hexdigest()
    from els_server.storage.profession_state import require_owner
    from els_server.storage.item_actor import require_active_character
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_active_character(db,owner);require_owner(db,owner,account)
        prior=db.execute('SELECT owner,digest FROM character_preset_receipts_v1 WHERE operation=?',(operation,)).fetchone()if exists(db,RECEIPTS)else None
        if prior is not None:
            if prior!=(owner,digest):raise ValueError('Conflicting preset retry')
        else:
            pages=snapshot(db,owner)
            if value['page']>len(pages):raise ValueError('Locked preset page')
            allowed=owned_pages(db,owner,account)
            if any(value[key]not in allowed[key]for key in wire.FIELDS):raise ValueError('Unowned referenced page')
            ensure_records(db)
            db.execute('CREATE TABLE IF NOT EXISTS character_preset_receipts_v1(operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,digest TEXT NOT NULL)')
            raw=json.dumps(value,sort_keys=True,separators=(',',':'))
            db.execute('INSERT INTO character_presets_v1 VALUES(?,?,?)ON CONFLICT(owner,page)DO UPDATE SET document=excluded.document',(owner,value['page'],raw))
            db.execute('INSERT INTO character_preset_receipts_v1 VALUES(?,?,?)',(operation,owner,digest))
        answers=[wire.acknowledgement(),wire.restoration(snapshot(db,owner))]
        for answer in answers:encode_event(answer)
        guard(db);require_active_character(db,owner);require_owner(db,owner,account)
        return answers


def expand(path,owner,account,payload,operation,guard):
    from els_server.protocol.career_messages import use_request,use_ack
    from els_server.domain.character_preset_coupons import SOURCES
    from els_server.storage.inventory_actions import _identity,_previous,_commit
    from els_server.storage.inventory_state import load_items
    from els_server.storage.equipment_receipt_state import current_changes
    from els_server.storage.item_instances import remove
    from els_server.storage.profession_state import require_owner
    from els_server.storage.item_actor import require_active_character
    source=use_request(payload)
    owner,digest=_identity(owner,0x219,b'preset-page-coupon:'+str(account).encode()+b':'+payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_owner(db,owner,account);require_active_character(db,owner)
        old=_previous(db,operation,digest);before=load_items(db,owner)
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0]
        if old is not None:
            changes=current_changes(db,operation,owner,0x219,old,before)
            answers=[use_ack(changes,ed=ed),wire.expanded(ed),wire.restoration(snapshot(db,owner))]
        else:
            item=next((i for i in before if i['uid']==source),None)
            if item is None or item['template']not in SOURCES:return None
            if item['group']!=4 or item['count']!=1 or item.get('sealed',False):raise ValueError('Preset coupon must be an unsealed owned singleton')
            from els_server.domain.item_expiration import require_current
            from els_server.domain.item_locks import require_unlocked
            require_current(item);require_unlocked(item)
            count=page_count(db,owner)
            if count>=4:raise ValueError('Preset maximum is four pages')
            ensure_records(db)
            db.execute('CREATE TABLE IF NOT EXISTS character_preset_capacity_v1(owner INTEGER PRIMARY KEY REFERENCES characters(uid) ON DELETE CASCADE,opened INTEGER NOT NULL CHECK(opened BETWEEN 2 AND 4))')
            db.execute('INSERT INTO character_preset_capacity_v1 VALUES(?,?)ON CONFLICT(owner)DO UPDATE SET opened=excluded.opened',(owner,count+1))
            remove(db,owner,item);remaining=None
            after=load_items(db,owner)
            answers=[use_ack([((item['group'],item['slot']),remaining)],item['template'],ed),wire.expanded(ed),wire.restoration(snapshot(db,owner))]
            _commit(db,operation,digest,owner,0x219,[(item['group'],item['slot'])],before,after)
        for answer in answers:encode_event(answer)
        guard(db);require_owner(db,owner,account);require_active_character(db,owner)
        return answers


def initialization(path,owner,account):
    from els_server.storage.read_scope import snapshot_connection
    from els_server.storage.profession_state import require_owner
    with snapshot_connection(path)as db:
        db.execute('BEGIN')
        require_owner(db,owner,account)
        return wire.restoration(snapshot(db,owner))
