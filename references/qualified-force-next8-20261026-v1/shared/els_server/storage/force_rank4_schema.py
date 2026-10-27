"""Expand only the known five-book CHECK, preserving its single child table.

The caller owns the transaction. Foreign keys stay enabled throughout; no
player rows, identifiers, receipts, seals or loadout selections are changed.
Unknown referencing tables fail closed before any DDL. This runs once per
old schema, not during read-only character projection.
"""
import re
import uuid

TABLE='selected_2026_force_inventory'
CHILD='selected_2026_force_slots'
OLD=((900401,3,295707),(900402,3,295712),(900406,3,306002),
     (900402,5,295714),(900406,5,306004))
ADDED=((900401,4,295708),(900402,4,295713),(900406,4,306003),(900401,5,295709),(900214,5,295729),(900234,5,295739),(900244,5,295744),(900269,5,311066),(900274,5,311515),(900279,5,311521),(900405,6,295762),(900408,5,311512),(900409,5,311518),(900410,5,311524),(900411,5,311527))
OLD_SEAL='CHECK(seal_used BETWEEN 0 AND 1 AND (rank=5 OR seal_used=0))'
PREVIOUS_SEAL='CHECK(seal_used BETWEEN 0 AND 3 AND ((rank=3 AND seal_used=0) OR (rank=4 AND seal_used<=3) OR (rank=5 AND seal_used<=1)))'
NEW_SEAL='CHECK(seal_used BETWEEN 0 AND 3 AND ((rank=3 AND seal_used=0) OR (rank=4 AND seal_used<=3) OR (rank=5 AND seal_used<=1) OR (rank=6 AND seal_used=0)))'


def _predicate(rows):
    return 'CHECK('+' OR '.join('(skill=%d AND rank=%d AND source_template=%d)'%r for r in rows)+')'


def _pattern(rows):
    return re.compile(re.escape(_predicate(rows)).replace(r'\ ',r'\s+'),re.I)


def _rows(db,table):
    return db.execute('SELECT * FROM '+table+' ORDER BY 1,2,3').fetchall()


def migrate(db):
    if not db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Force schema migration requires caller transaction with foreign keys enabled')
    sql=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone()[0]
    seal=re.compile(re.escape(OLD_SEAL).replace(r'\ ',r'\s+'),re.I)
    new_seal=re.compile(re.escape(NEW_SEAL).replace(r'\ ',r'\s+'),re.I)
    complete=_pattern(OLD+ADDED)
    if complete.search(sql) and new_seal.search(sql):return
    old=_pattern(OLD);interim=_pattern(OLD+ADDED[:3]);previous=_pattern(OLD+ADDED[:4]);active_v2=_pattern(OLD+ADDED[:7]);master_v1=_pattern(OLD+ADDED[:10]);passive_v1=_pattern(OLD+ADDED[:7]+ADDED[10:])
    previous_seal=re.compile(re.escape(PREVIOUS_SEAL).replace(r'\ ',r'\s+'),re.I)
    if len(old.findall(sql))!=1 and not interim.search(sql) and not complete.search(sql) and not previous.search(sql) and not active_v2.search(sql) and not master_v1.search(sql) and not passive_v1.search(sql):raise ValueError('Unknown force ownership CHECK; keep schema unchanged')
    if len(seal.findall(sql))!=1 and not new_seal.search(sql) and not previous_seal.search(sql):raise ValueError('Unknown force seal CHECK; keep schema unchanged')
    columns=[r[1] for r in db.execute('PRAGMA table_info('+TABLE+')')]
    if columns!=['owner','skill','rank','source_template','seal_used']:
        raise ValueError('Unknown force ownership columns')
    names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    references={n for n in names for f in db.execute('PRAGMA foreign_key_list("'+n.replace('"','""')+'")') if f[2] in (TABLE,CHILD)}
    if references-{CHILD}:raise ValueError('Unknown force schema references')
    child=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(CHILD,)).fetchone()
    if child and [r[1] for r in db.execute('PRAGMA table_info('+CHILD+')')]!=['owner','slot','skill','rank']:
        raise ValueError('Unknown force loadout columns')
    before=_rows(db,TABLE);slots=_rows(db,CHILD) if child else None
    objects=db.execute("SELECT type,name,sql FROM sqlite_master WHERE tbl_name IN (?,?) AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type,name",(TABLE,CHILD)).fetchall()
    # Both known tables use composite keys, never AUTOINCREMENT. Sequence and
    # unrelated schema/data remain untouched, including any existing sequence.
    if 'AUTOINCREMENT' in sql.upper() or child and 'AUTOINCREMENT' in child[0].upper():
        raise ValueError('Unexpected force sequence')
    temp='force_inventory_rank4_'+uuid.uuid4().hex
    rewritten=old.sub(_predicate(OLD+ADDED),sql,count=1)
    rewritten=interim.sub(_predicate(OLD+ADDED),rewritten,count=1)
    rewritten=previous.sub(_predicate(OLD+ADDED),rewritten,count=1)
    rewritten=active_v2.sub(_predicate(OLD+ADDED),rewritten,count=1)
    rewritten=master_v1.sub(_predicate(OLD+ADDED),rewritten,count=1)
    rewritten=passive_v1.sub(_predicate(OLD+ADDED),rewritten,count=1)
    rewritten=previous_seal.sub(NEW_SEAL,rewritten,count=1)
    rewritten=seal.sub(NEW_SEAL,rewritten,count=1).replace(TABLE,temp,1)
    # Ownership CHECK expansion does not widen native passive/Mod slots.
    # Preserve either prior3-slot schema or historical11-slot schema exactly.
    savepoint='force_rank4_'+uuid.uuid4().hex
    db.execute('SAVEPOINT '+savepoint)
    try:
        db.execute(rewritten)
        db.execute('INSERT INTO '+temp+' SELECT * FROM '+TABLE)
        if child:db.execute('DROP TABLE '+CHILD)
        db.execute('DROP TABLE '+TABLE)
        db.execute('ALTER TABLE '+temp+' RENAME TO '+TABLE)
        if child:
            db.execute(child[0])
            db.executemany('INSERT INTO '+CHILD+' VALUES (?,?,?,?)',slots)
        for _,_,statement in objects:db.execute(statement)
        if _rows(db,TABLE)!=before or child and _rows(db,CHILD)!=slots:
            raise ValueError('Force migration changed persisted ownership/loadout')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Force migration foreign-key integrity')
        restored=db.execute("SELECT type,name,sql FROM sqlite_master WHERE tbl_name IN (?,?) AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type,name",(TABLE,CHILD)).fetchall()
        if restored!=objects:raise ValueError('Force migration changed index/trigger definitions')
        db.execute('RELEASE '+savepoint)
    except BaseException:
        db.execute('ROLLBACK TO '+savepoint);db.execute('RELEASE '+savepoint)
        raise

