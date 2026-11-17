"""Durable sealed pet results in the caller's existing result transaction."""
import json


def seal(db,match_id,winner,account,ended_at,fact,guard):
    if not db.in_transaction or not callable(guard):raise ValueError('Pet result SQL writer required')
    guard(db)
    if fact['winner']!=winner or fact['mode']not in('random','invited'):
        raise ValueError('Pet result sealed mode/winner')
    participants=fact['participants']
    if len(participants)!=2 or len({p['account']for p in participants})!=2:
        raise ValueError('Pet result distinct original accounts')
    winning=next(p for p in participants if p['uid']==winner)
    losing=next(p for p in participants if p['uid']!=winner)
    if winning['account']!=account or not any(p['hp']for p in winning['pets'])or any(p['hp']for p in losing['pets']):
        raise ValueError('Pet result requires server-owned all-three-pets-fainted finish')
    raw=json.dumps(fact,sort_keys=True,separators=(',',':'))
    db.execute('''CREATE TABLE IF NOT EXISTS pet_battle_results(
        match_id TEXT PRIMARY KEY,winner INTEGER NOT NULL REFERENCES characters(uid),
        account INTEGER NOT NULL,ended_at INTEGER NOT NULL,fact_json TEXT NOT NULL)''')
    previous=db.execute('SELECT winner,account,ended_at,fact_json FROM pet_battle_results WHERE match_id=?',(match_id,)).fetchone()
    expected=(winner,account,ended_at,raw)
    if previous is not None:
        if previous!=expected:raise ValueError('Pet sealed result retry changed')
        return False
    db.execute('INSERT INTO pet_battle_results VALUES(?,?,?,?,?)',(match_id,*expected))
    guard(db)
    return True
