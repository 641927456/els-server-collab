"""Read retained growth history only through the original adoption audit."""
from els_server.storage.resonance_2026_progress import AccountResonance

def audited(db,account,kind,identity):
    if kind not in ('join','task'):raise ValueError('Growth audit kind')
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'resonance2026_legacy_growth_audit' not in tables:return False
    table='boosting2026_join_rewards' if kind=='join' else 'boosting2026_task_rewards'
    sql='SELECT * FROM '+table+' WHERE account=?'+(' AND quest=?' if kind=='task' else '')
    row=db.execute(sql,(account,identity) if kind=='task' else (account,)).fetchone()
    old=db.execute('SELECT row_sha256 FROM resonance2026_legacy_growth_audit WHERE account=? AND kind=? AND identity=?',(account,kind,identity)).fetchone()
    if row is None or old!=(AccountResonance._legacy_digest(row),):return False
    # _read already verifies the retained legacy balance and formal dominance.
    legacy=db.execute('SELECT revision,cumulative_experience FROM resonance2026_accounts WHERE account=?',(account,)).fetchone()
    if legacy is None:return False
    if kind=='join':revision,total=row[5],row[7]
    else:
        import json
        effect=json.loads(row[4]).get('effect')
        if type(effect)is not dict:return False
        revision,level,total=effect['after']
    return type(revision)is int and type(total)is int and 0<=revision<=legacy[0] and 0<=total<=legacy[1]
