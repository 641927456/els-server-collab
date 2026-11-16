"""One owned Lu/Ciel role for client-origin wire acceptance, without a native claim."""
from contextlib import closing
import sqlite3,struct

def enroll(row,index,path,operation):
    from els_server.storage.characters import Characters
    from els_server.storage.local_state import LocalState
    from els_server.storage.reward_state import RewardState
    from els_server.game_data import client_data
    from els_server.storage import resonance_state as resonance
    from els_server.domain.resonance import curve
    from els_server.storage.boosting_2026_force_inventory import initialize
    from els_server.storage.boosting_2026_force_equipment import action
    from els_server.domain.character_rules import default_slots,validate_career_state
    from els_server.storage.erp_support_quest_scope import _table_snapshot
    name='P200'+format(row['account_id'],'x')
    roles=Characters(path,row['account_id']);uid=roles.create(name,10,operation+':power')['uid']
    RewardState(path,uid,account_id=row['account_id']);LocalState(path,uid).save(20000,0,0,(1.,2.,3.))
    with closing(sqlite3.connect(path,timeout=60))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE characters SET unit_class=179,level=99,transcendence=1,master=0 WHERE uid=?',(uid,))
        db.execute('UPDATE reward_balances SET experience=?,ed=1000 WHERE uid=?',(client_data().thresholds[-1],uid))
        resonance.ensure(db)
        before=curve()[200]['TOTAL_ER_EXP']-1
        db.execute('INSERT INTO account_resonance VALUES(?,1,?,1) ON CONFLICT(account_id) DO UPDATE SET enabled=1,experience=excluded.experience,revision=revision+1',(row['account_id'],before))
        initialize(db)
        db.execute('INSERT INTO selected_2026_force_inventory(owner,skill,rank,source_template,seal_used) VALUES(?,?,5,306009,0)',(uid,900407))
        with _table_snapshot(db):character,=roles._project_rows(db,uid)
        validate_career_state(character)
        db.execute('INSERT INTO skill_slots VALUES(?,?,1) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload',(uid,struct.pack('>22i',*default_slots(character))))
    ack=action(path,uid,row['account_id'],struct.pack('>iiiB',1,0,900407,5),operation+':power-force')
    assert ack.kind==0x6d1 and ack.payload[:4]==bytes(4)
    row.update(uid=uid,unit=10,target=179,town=20000,character_name=name,scenario='client_power',index=index,power_before_exp=before)

def cold(row,path,*,retired=False):
    from els_server.domain.resonance import level
    from els_server.storage.luciel_state import active_state
    with closing(sqlite3.connect(path,timeout=60))as db:
        db.execute('PRAGMA query_only=ON')
        uid=row['uid'];assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(row['account_id'],)
        assert db.execute('SELECT unit_type,unit_class,level,transcendence FROM characters WHERE uid=?',(uid,)).fetchone()==(10,179,99,1)
        facts=db.execute('SELECT active_side,raw_power,basis_points,run_id FROM greed_power_facts WHERE owner=? ORDER BY active_side',(uid,)).fetchall()
        expected=[(0,3999.5,2000)]+([(1,4000.5,2500)]if retired else [])
        assert [fact[:3]for fact in facts]==expected,facts
        assert len({fact[3]for fact in facts})==len(expected)
        er=db.execute('SELECT experience FROM account_resonance WHERE account_id=?',(row['account_id'],)).fetchone()[0]
        assert er>row['power_before_exp'] and level(er)==201
        assert active_state(db,uid)['active_unit']==int(retired)
        kills=db.execute('SELECT count(*) FROM pve_kill_experience WHERE owner=?',(uid,)).fetchone()[0]
        assert kills==len(expected)
        return dict(scenario='client_power',ok=True,read_only=True,client_origin_fixture=True,native_session=False,current_form_unrounded=True,facts=[dict(side=f[0],raw=f[1],basis_points=f[2])for f in facts],ERP_level=201,kill_receipts=kills,replayed_without_extra_fact=True)
