"""Freeze a current owned effect snapshot inside the original reward writer."""
import hashlib,json,time
from els_server.domain.elixir_economy import effects

TABLE='elixir_economy_facts'
SQL='CREATE TABLE elixir_economy_facts(operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),dungeon INTEGER NOT NULL,kind TEXT NOT NULL,context_sha256 TEXT NOT NULL,basis_points INTEGER NOT NULL,settled_at INTEGER NOT NULL,effects_json TEXT NOT NULL)'

def _validate(db,owner,identity,kind,when,amount,rows):
    from els_server.domain.elixir_economy import policy
    from els_server.storage.world_elixirs import _source
    rules={r['template']:r for r in policy()['rows']}
    if not isinstance(rows,list)or not rows or len({r['template']for r in rows})!=len(rows):raise ValueError('Elixir economic source snapshot')
    for row in rows:
        r=rules.get(row['template'])
        if r is None or identity in r['disabled_dungeons']or row['basis_points']!=r[kind+'_bp']or not row['basis_points']or not row['start']<=when<row['end']or row['end']-row['start']!=r['period_seconds']:raise ValueError('Elixir economic exact source effect')
        _source(db,row['source_operation'],owner,row['source_uid'],row['template'])
    if sum(r['basis_points']for r in rows)!=amount:raise ValueError('Elixir economic source sum')

def _elixir_bonus(db,owner,identity,kind,operation,context,*,already_issued=False,now=None):
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.bank_state import account_for
    from els_server.domain.elixir_economy import eligible
    if not db.in_transaction or type(owner)is not int or type(operation)is not str or not 1<=len(operation)<=200 or kind not in('experience','drop')or type(context)is not dict:raise ValueError('Elixir original economic writer')
    require_active_character(db,owner);account_for(db,owner)
    canonical=json.dumps(context,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(canonical.encode()).hexdigest()
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone()
    prior=db.execute('SELECT owner,dungeon,kind,context_sha256,basis_points,settled_at,effects_json FROM elixir_economy_facts WHERE operation=?',(operation,)).fetchone()if exists else None
    if prior:
        if prior[:4]!=(owner,identity,kind,digest)or type(prior[4])is not int or not 0<prior[4]<=10000:raise ValueError('Changed elixir economic receipt')
        saved=json.loads(prior[6]);_validate(db,owner,identity,kind,prior[5],prior[4],saved)
        return prior[4]
    # Historical source receipts predate this extension. New buffs must never
    # change an already-issued draw or restart a settled EXP award.
    if already_issued or not eligible(identity):return 0
    when=int(time.time())if now is None else now
    if type(when)is not int or not 0<when<2**31:raise ValueError('Elixir economic clock')
    from els_server.storage.world_elixirs import _state
    state=_state(db,owner,when);amount,selected=effects(state['rows'],identity,kind)
    if not amount:return 0
    for row in selected:
        group=row['template']
        table='world_elixir_economy_state'if group in(190401,310775,310776)else'world_elixir_state'
        source=db.execute('SELECT operation_id FROM '+table+' WHERE owner=? AND template=? AND source_uid=? AND starts_at=? AND ends_at=?',(owner,row['template'],row['source_uid'],row['start'],row['end'])).fetchall()
        if len(source)!=1:raise ValueError('Elixir current economic source lineage')
        row['source_operation']=source[0][0]
    _validate(db,owner,identity,kind,when,amount,selected)
    db.execute(SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
    db.execute('INSERT INTO elixir_economy_facts VALUES(?,?,?,?,?,?,?,?)',(operation,owner,identity,kind,digest,amount,when,json.dumps(selected,sort_keys=True,separators=(',',':'))))
    return amount

def bonus(db,owner,identity,kind,operation,context,*,already_issued=False,now=None):
    # The existing elixir snapshot remains unchanged. An old elixir fact with
    # no medal fact predates this extension and must not acquire a new bonus.
    old=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()and db.execute('SELECT 1 FROM elixir_economy_facts WHERE operation=?',(operation,)).fetchone())
    from els_server.storage.held_medals import bonus as held_bonus
    old_medal=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='held_medal_reward_facts'").fetchone()and db.execute('SELECT 1 FROM held_medal_reward_facts WHERE operation=?',(operation,)).fetchone())
    medal=held_bonus(db,owner,identity,kind,operation,context,already_issued=already_issued or old,now=now)
    elixir=_elixir_bonus(db,owner,identity,kind,operation,context,already_issued=already_issued or old_medal,now=now)
    if not 0<=medal+elixir<=15000:raise ValueError('Combined held medal/elixir percentage')
    return medal+elixir
