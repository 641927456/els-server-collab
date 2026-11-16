"""Freeze guild economic effects in the existing accepted reward transaction."""
import hashlib,json,time
from els_server.storage.guild_system_state import exists
from els_server.domain import guild_services

TABLE='native_guild_economic_facts_v2'


def present(db,operation):
    return bool(exists(db,TABLE)and db.execute('SELECT 1 FROM native_guild_economic_facts_v2 WHERE operation=?',(operation,)).fetchone())


def bonus(db,owner,dungeon,kind,operation,context,*,already_issued=False,now=None):
    if not db.in_transaction or kind not in('experience','drop'):raise ValueError('Guild effect original reward transaction')
    digest=hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    old=db.execute('SELECT owner,dungeon,kind,context_hash,basis_points,created_at,effects FROM native_guild_economic_facts_v2 WHERE operation=?',(operation,)).fetchone()if exists(db,TABLE)else None
    if old:
        if old[:4]!=(owner,dungeon,kind,digest):raise ValueError('Conflicting guild economic operation')
        effects=json.loads(old[6])
        for row in effects['services']:
            if not row['start']<=old[5]<row['end']:raise ValueError('Expired frozen guild effect')
            guild_services.source(db,row['guild'],row['template'],dict(template=guild_services.BUFFS[row['template']][0],start=row['start'],end=row['end'],operation=row['source_operation']))
        if old[4]!=effects[kind+'_bp']:raise ValueError('Guild economic amount differs from source')
        return old[4]
    from els_server.domain.elixir_economy import eligible
    if already_issued or not eligible(dungeon):return 0
    from els_server.storage.bank_state import account_for
    from els_server.storage.item_actor import require_active_character
    require_active_character(db,owner);account=account_for(db,owner)
    when=int(time.time())if now is None else now
    from els_server.domain.guild_effects import economic
    effects=economic(db,owner,account,when);amount=effects[kind+'_bp']
    if not 0<=amount<=(7500 if kind=='experience'else 2000):raise ValueError('Guild sourced economic maximum')
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_economic_facts_v2(
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),dungeon INTEGER NOT NULL,
        kind TEXT NOT NULL,context_hash TEXT NOT NULL,basis_points INTEGER NOT NULL,
        created_at INTEGER NOT NULL,effects TEXT NOT NULL)''')
    db.execute('INSERT INTO native_guild_economic_facts_v2 VALUES(?,?,?,?,?,?,?,?)',
        (operation,owner,dungeon,kind,digest,amount,when,json.dumps(effects,sort_keys=True,separators=(',',':'))))
    return amount
