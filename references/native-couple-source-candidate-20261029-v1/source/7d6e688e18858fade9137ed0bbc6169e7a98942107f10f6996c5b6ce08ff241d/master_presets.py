"""One-time recovery of the previously unsupported dedicated Master preset."""
import sqlite3,struct
from contextlib import closing
from els_server.domain.role_progression import first_master_skill,known_skills
from els_server.domain.skill_state import encode_slots
from els_server.domain.skill_rules import equippable_skills,upgraded_slots


def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS master_preset_migrations (owner INTEGER PRIMARY KEY, skill_id INTEGER NOT NULL)')


def mark(db,character):
    skill=first_master_skill(character)
    if not skill:return
    ensure(db)
    db.execute('INSERT INTO master_preset_migrations VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET skill_id=excluded.skill_id',(character['uid'],skill))


def repair(path):
    from els_server.storage.skill_expansion import is_expanded
    from els_server.domain.character_rules import default_slots
    restored=[]
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');ensure(db)
        rows=list(db.execute('SELECT uid,unit_class,level,transcendence FROM characters WHERE master=1 AND uid NOT IN (SELECT owner FROM master_preset_migrations)'))
        for uid,cls,level,tc in rows:
            c=dict(uid=uid,unit_class=cls,level=level,transcendence=bool(tc),master=True,skill_row_expanded=is_expanded(db,uid))
            from els_server.storage.skill_unlocks import saved_groups
            c['skill_seal_groups']=saved_groups(db,uid)
            from els_server.domain.relationship_skills import saved as relationship_saved
            c['relationship']=relationship_saved(db,uid)
            skill=first_master_skill(c)
            if not skill or not tc or level!=99:raise ValueError('Invalid saved Master identity')
            old=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(uid,)).fetchone()
            if old:
                if len(old[0])!=88:raise ValueError('Invalid saved Master preset size')
                slots=list(struct.unpack('>22i',old[0]))
                if any(s and s not in known_skills(cls) for s in slots):raise ValueError('Unknown saved Master skill')
                slots=list(upgraded_slots(slots,c))
                if not slots[21]:slots[21]=skill
            else:slots=default_slots(c)
            visible=encode_slots(slots,equippable_skills(c),c)
            from els_server.domain.relationship_skills import persisted_slots
            previous=struct.unpack('>22i',old[0])if old else (0,)*22
            encoded=struct.pack('>22i',*persisted_slots(previous,struct.unpack('>22i',visible),c))
            db.execute('INSERT INTO skill_slots VALUES (?,?,1) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload,revision=revision+1 WHERE payload<>excluded.payload',(uid,encoded))
            mark(db,c);restored.append(uid)
    return restored
