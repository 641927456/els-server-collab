"""Transactional migration of the original single-character save constraints."""
import re

TABLE_KEYS={'location':'uid','ui_layout':'uid','key_bindings':'uid',
            'skill_slots':'uid','reward_balances':'uid','inventory_items':'owner'}

def character_uid(value):
    if type(value) is not int or not 1001<=value<2**63-1:
        raise ValueError('Invalid character UID')
    return value

def stored_character_type(db,uid):
    """Read the owner inside the caller's transaction; support legacy test saves."""
    character_uid(uid)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='characters'").fetchone():
        if uid==1001:return 1
        raise ValueError('Unknown character')
    row=db.execute('SELECT unit_type FROM characters WHERE uid=?',(uid,)).fetchone()
    if row is None:raise ValueError('Unknown character')
    return row[0]

def migrate_character_schema(db):
    """Caller owns the transaction; preserve rows, indexes and receipts."""
    for table,key in TABLE_KEYS.items():
        row=db.execute('SELECT sql FROM sqlite_master WHERE type=\'table\' AND name=?',(table,)).fetchone()
        if row is None:continue
        sql=row[0]
        old=f'CHECK({key}=1001)'
        if old not in sql:continue
        indexes=db.execute('SELECT sql FROM sqlite_master WHERE type=\'index\' AND tbl_name=? AND sql IS NOT NULL',(table,)).fetchall()
        temp=table+'_multi_migration'
        new_sql=re.sub(r'^(CREATE TABLE\s+)(?:"?'+table+r'"?)',r'\1'+temp,sql,count=1,flags=re.I)
        if new_sql==sql:raise ValueError('Unrecognized legacy character schema')
        db.execute(new_sql.replace(old,f'CHECK({key}>=1001)'))
        db.execute(f'INSERT INTO {temp} SELECT * FROM {table}')
        before=db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        after=db.execute(f'SELECT COUNT(*) FROM {temp}').fetchone()[0]
        if before!=after:raise ValueError('Character migration row count mismatch')
        db.execute(f'DROP TABLE {table}')
        db.execute(f'ALTER TABLE {temp} RENAME TO {table}')
        for index in indexes:db.execute(index[0])
