"""Only three newly allocated QA owners; no player database replacement."""
from pathlib import Path
from contextlib import closing
import json,sqlite3

def seed(path,actors):
    from els_server.storage.local_state import LocalState
    from els_server.domain.town_travel import catalog
    from els_server.game_data import client_data
    assert len(actors)==3 and len({a['uid']for a in actors})==len({a['account_id']for a in actors})==3
    for index,a in enumerate(actors):
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(a['uid'],)).fetchone()==(a['account_id'],)
            if index==0:
                db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(a['uid'],))
                db.execute('UPDATE reward_balances SET ed=6000000,experience=? WHERE uid=?',(client_data().thresholds[98],a['uid']))
        LocalState(path,a['uid']).save(20001,0,0,catalog()['towns']['20001']['xyz'])

def snapshot(path,actors):
    from els_server.storage.inventory_state import load_items
    from els_server.storage.npc_trade import balances
    from els_server.storage import guild_membership_state
    rows=[];uids={a['uid']for a in actors}
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as db:
        db.execute('BEGIN');tables={n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        receipts=[]
        if 'native_duel_results'in tables:
            for raw, in db.execute('SELECT result_json FROM native_duel_results'):
                value=json.loads(raw)
                if any(m['uid']in uids for m in value['proof']['members']):
                    assert all(m['uid']in uids for m in value['proof']['members'])
                    receipts.append(dict(seed=value['proof']['seed'],reason=value['proof']['reason'],rows=[{k:r[k]for k in('uid','rating_delta','ap_delta','awarded_exp')}for r in value['rows']]))
        for a in actors:
            uid=a['uid'];account=a['account_id']
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
            refusals=[]if'native_duel_refusals'not in tables else db.execute('SELECT inviter,recipient,generation,until FROM native_duel_refusals WHERE inviter=? OR recipient=?ORDER BY inviter,recipient',(uid,uid)).fetchall()
            official=None if'official_pvp_profiles'not in tables else db.execute('SELECT profile_json FROM official_pvp_profiles WHERE uid=?',(uid,)).fetchone()
            rows.append(dict(uid=uid,items=load_items(db,uid),money=balances(db,uid),location=db.execute('SELECT town,board,progress,x,y,z FROM location WHERE uid=?',(uid,)).fetchone(),guild=guild_membership_state.snapshot(db,uid,account),
                duels=[r for r in receipts if any(v['uid']==uid for v in r['rows'])],refusals=refusals,official=official,
                quests=db.execute('SELECT *FROM character_quests WHERE owner=?ORDER BY quest',(uid,)).fetchall()))
    return rows
