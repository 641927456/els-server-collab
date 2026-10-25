"""Per-character per-dungeon daily baseline and paid first-double, atomically."""
import json,time

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS ariel_daily_special_counts (owner INTEGER NOT NULL REFERENCES characters(uid),dungeon INTEGER NOT NULL,day INTEGER NOT NULL,count INTEGER NOT NULL CHECK(count>=1 AND count<=2),PRIMARY KEY(owner,dungeon,day))')
    db.execute('CREATE TABLE IF NOT EXISTS ariel_daily_special_receipts (run_id TEXT PRIMARY KEY REFERENCES reward_receipts(run_id),owner INTEGER NOT NULL,detail_json TEXT NOT NULL)')

def lookup(db,run_id,owner):
    row=db.execute('SELECT owner,detail_json FROM ariel_daily_special_receipts WHERE run_id=?',(run_id,)).fetchone()
    if row is None or row[0]!=owner:raise ValueError('Ariel daily receipt owner')
    return json.loads(row[1])

def grant(db,value,owner,run_id,dungeon_clear,*,now=time.time):
    from els_server.domain.ariel_daily_special import DailySpecialClear
    from els_server.domain.ariel_daily_special_rules import plans
    from els_server.storage.ariel_attendance import owner as require_owner,state,day,clock
    from els_server.storage.inventory_state import ensure_inventory,migrate_fashion_bag,migrate_potion_bag,grant_items
    if (not db.in_transaction or type(value)is not DailySpecialClear or value.character!=owner
        or value.reward_run_id!=run_id or dungeon_clear is None or dungeon_clear[0]!=value.dungeon):raise ValueError('Ariel daily typed clear transaction')
    r=value.validate();require_owner(db,value.account,owner)
    # The caller already holds SQLite's writer lock. One authoritative time
    # samples the CN10 boundary and paid entitlement in this transaction.
    moment=clock(now);today=day(moment);current=state(db,value.account,moment)
    initialize(db)
    if db.execute('SELECT 1 FROM ariel_daily_special_counts WHERE owner=? AND day>?',(owner,today)).fetchone():raise ValueError('Ariel daily saved future day')
    row=db.execute('SELECT count FROM ariel_daily_special_counts WHERE owner=? AND dungeon=? AND day=?',(owner,value.dungeon,today)).fetchone()
    before=0 if row is None else row[0]
    if type(before)is not int or not 0<=before<=r['daily_count']:raise ValueError('Ariel daily saved count')
    awarded=[];multiplier=1;after=before
    if before<r['daily_count']:
        multiplier=2 if before==0 and current['active']else 1
        plan=plans(value.dungeon,value.unit,multiplier)
        ensure_inventory(db);migrate_fashion_bag(db);migrate_potion_bag(db)
        source=_DailySource(_DAILY_FACTORY_SEAL,db,value,moment,before,current,plan)
        try:awarded=grant_items(db,plan,owner,daily_special_source=source)
        finally:source.close()
        after=before+1
        db.execute('INSERT INTO ariel_daily_special_counts VALUES (?,?,?,?) ON CONFLICT(owner,dungeon,day) DO UPDATE SET count=excluded.count',(owner,value.dungeon,today,after))
    detail=dict(owner=owner,account=value.account,dungeon=value.dungeon,day=today,before=before,after=after,quota=r['daily_count'],
        multiplier=multiplier,premium_period=current['purchase_id']if current['active']else None,grant=before<r['daily_count'])
    value.validate();require_owner(db,value.account,owner)
    return detail,awarded,notification(db,value.account,owner,moment)

def notification(db,account,owner,moment):
    from els_server.domain.ariel_daily_special_rules import data,rule
    from els_server.storage.ariel_attendance import owner as require_owner,day
    from els_server.protocol.ariel_daily_special_messages import notification as encode
    from els_server.protocol.protocol_codec import encode_event
    if not db.in_transaction or type(moment)is not int or not 0<=moment<2**40:raise ValueError('Normal daily snapshot transaction/clock')
    require_owner(db,account,owner);today=day(moment)
    catalog={int(k):rule(int(k))for k in data()['maps']}
    if len(catalog)!=20 or any(v is None or v['dungeon_type']!=0 for v in catalog.values()):raise ValueError('Normal daily full provider')
    counts={}
    entry=db.execute("SELECT type FROM sqlite_master WHERE name='ariel_daily_special_counts'").fetchone()
    if entry is not None:
        expected=[('owner','INTEGER',1,1),('dungeon','INTEGER',1,2),('day','INTEGER',1,3),('count','INTEGER',1,0)]
        if entry!=('table',)or [(r[1],r[2],r[3],r[5])for r in db.execute('PRAGMA table_info(ariel_daily_special_counts)')]!=expected:raise ValueError('Normal daily unknown saved schema')
        # Inspect all this owner's historical rows too: unknown authority is
        # refused, never omitted from a replacement map or removed from SQL.
        for dungeon,saved_day,count in db.execute('SELECT dungeon,day,count FROM ariel_daily_special_counts WHERE owner=?',(owner,)):
            if(any(type(v)is not int for v in(dungeon,saved_day,count))or dungeon not in catalog
                or not -1<=saved_day<=today or not 1<=count<=catalog[dungeon]['daily_count']):raise ValueError('Normal daily unknown or invalid saved authority')
            if saved_day==today:counts[dungeon]=count
    rows=tuple((d,counts.get(d,0),catalog[d]['daily_count'])for d in sorted(catalog))
    from els_server.storage.silver_mirror_state import read as mirror_state
    mirror=mirror_state(db,owner,now=moment)
    answer=encode(rows,moment,mirror_remaining=mirror['remaining']);encode_event(answer);require_owner(db,account,owner)
    return answer

def snapshot(path,account,owner,*,validate,now=time.time):
    from els_server.storage.ariel_cash import reading
    from els_server.storage.ariel_attendance import clock
    validate()
    with reading(path)as db:
        answer=notification(db,account,owner,clock(now));validate();return answer

def save(db,run_id,owner,detail):
    db.execute('INSERT INTO ariel_daily_special_receipts VALUES (?,?,?)',(run_id,owner,json.dumps(detail,sort_keys=True,separators=(',',':'))))

# Only the original daily writer issues this ephemeral authority, after count,
# entitlement and the exact native plan have been resolved in that transaction.
_DAILY_FACTORY_SEAL=object()
_DAILY_SHARED_MATERIALS=frozenset((135879,135882,135885))

class _DailySource:
    __slots__=('_seal','_db','_value','_moment','_before','_current','_plan','_used','_alive','_path','_savepoint','owner')
    def __init__(self,seal,db,value,moment,before,current,plan):
        if seal is not _DAILY_FACTORY_SEAL:raise ValueError('Private daily source constructor')
        self._seal=seal;self._db=db;self._value=value;self._moment=moment;self._before=before
        self._current=json.dumps(current,sort_keys=True);self._plan=json.dumps(plan,sort_keys=True)
        from pathlib import Path
        import sqlite3,uuid
        if type(db)is not sqlite3.Connection or not db.in_transaction:raise ValueError('Daily source original writer required')
        self._used=False;self._alive=True;self.owner=value.character
        self._path=Path(value.session.account.store.path).resolve()
        self._savepoint='ariel_daily_source_'+uuid.uuid4().hex
        db.execute('SAVEPOINT '+self._savepoint)
        self._validate()
    def _validate(self):
        import sqlite3
        from pathlib import Path
        from els_server.storage.ariel_attendance import owner,state,day
        if self._seal is not _DAILY_FACTORY_SEAL or not self._alive or type(self._db)is not sqlite3.Connection or not self._db.in_transaction:
            raise ValueError('Daily source outside original writer lifetime')
        value=self._value;r=value.validate();owner(self._db,value.account,self.owner)
        main=[row[2]for row in self._db.execute('PRAGMA database_list')if row[1]=='main']
        if len(main)!=1 or Path(main[0]).resolve()!=self._path or Path(value.session.account.store.path).resolve()!=self._path:
            raise ValueError('Daily source original database changed')
        # COMMIT/ROLLBACK drops this marker. Never recreate it after failure,
        # even when the same connection begins again with identical rows.
        self._db.execute('RELEASE SAVEPOINT '+self._savepoint)
        self._db.execute('SAVEPOINT '+self._savepoint)
        today=day(self._moment)
        row=self._db.execute('SELECT count FROM ariel_daily_special_counts WHERE owner=? AND dungeon=? AND day=?',(self.owner,value.dungeon,today)).fetchone()
        if (0 if row is None else row[0])!=self._before or not 0<=self._before<r['daily_count']:
            raise ValueError('Daily source original quota changed')
        current=state(self._db,value.account,self._moment)
        if json.dumps(current,sort_keys=True)!=self._current:raise ValueError('Daily source original entitlement changed')
        from els_server.domain.ariel_daily_special_rules import plans
        multiplier=2 if self._before==0 and current['active']else 1
        if json.dumps(plans(value.dungeon,value.unit,multiplier),sort_keys=True)!=self._plan:
            raise ValueError('Daily source original plan changed')
        return self
    def validate_plan(self,plan):
        self._validate()
        if json.dumps(plan,sort_keys=True)!=self._plan:raise ValueError('Daily source exact plan required')
        return self
    def validate_template(self,template):
        self._validate()
        if type(template)is not int or template not in {p['template']for p in json.loads(self._plan)}:
            raise ValueError('Daily source template outside exact plan')
        return template in _DAILY_SHARED_MATERIALS
    def bind_factory(self,db,owner,plan):
        if self._used or db is not self._db or type(owner)is not int or owner!=self.owner:
            raise ValueError('Daily source foreign/reused factory')
        self.validate_plan(plan);self._used=True
    def close(self):
        if self._alive:
            self._alive=False;self._db.execute('RELEASE SAVEPOINT '+self._savepoint)

def validate_source(source):
    if type(source)is not _DailySource:raise ValueError('Typed original daily source required')
    return source._validate()
