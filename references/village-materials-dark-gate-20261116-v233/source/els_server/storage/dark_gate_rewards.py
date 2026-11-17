"""An allied-gate defeat spends the same daily chance as a successful clear."""
import hashlib,json

TABLE='dark_gate_failure_receipts'

def require_not_failed(db,run_id):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone():
        if db.execute('SELECT 1 FROM dark_gate_failure_receipts WHERE run_id=?',(run_id,)).fetchone():
            raise ValueError('Dark Gate failed run cannot become a reward clear')

def consume(db,account,owner,run_id,proof,moment):
    from els_server.storage.ariel_attendance import owner as require_owner,day
    from els_server.storage.ariel_daily_special import initialize
    from els_server.domain.ariel_daily_special_rules import rule
    import uuid
    if (not db.in_transaction or type(proof)is not bytes or not proof
        or type(moment)is not int or not 0<=moment<2**40 or str(uuid.UUID(run_id))!=run_id):
        raise ValueError('Dark Gate failure transaction/source')
    require_owner(db,account,owner);initialize(db)
    db.execute('CREATE TABLE IF NOT EXISTS dark_gate_failure_receipts (run_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account INTEGER NOT NULL,proof_sha256 TEXT NOT NULL,detail_json TEXT NOT NULL)')
    hashed=hashlib.sha256(proof).hexdigest()
    old=db.execute('SELECT owner,account,proof_sha256,detail_json FROM dark_gate_failure_receipts WHERE run_id=?',(run_id,)).fetchone()
    if old is not None:
        if old[:3]!=(owner,account,hashed):raise ValueError('Dark Gate conflicting failure replay')
        return json.loads(old[3])
    if db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(run_id,)).fetchone():
        raise ValueError('Dark Gate rewarded run cannot become a failure')
    today=day(moment);quota=rule(38300)['daily_count']
    if db.execute('SELECT 1 FROM ariel_daily_special_counts WHERE owner=? AND day>?',(owner,today)).fetchone():
        raise ValueError('Dark Gate saved future day')
    row=db.execute('SELECT count FROM ariel_daily_special_counts WHERE owner=? AND dungeon=38300 AND day=?',(owner,today)).fetchone()
    before=0 if row is None else row[0]
    if type(before)is not int or not 0<=before<=quota:raise ValueError('Dark Gate saved count')
    after=min(quota,before+1)
    if after!=before:
        db.execute('INSERT INTO ariel_daily_special_counts VALUES (?,38300,?,?) ON CONFLICT(owner,dungeon,day) DO UPDATE SET count=excluded.count',(owner,today,after))
    detail=dict(account=account,owner=owner,dungeon=38300,day=today,before=before,after=after,quota=quota,grant=False)
    db.execute('INSERT INTO dark_gate_failure_receipts VALUES (?,?,?,?,?)',(run_id,owner,account,hashed,json.dumps(detail,sort_keys=True)))
    return detail
