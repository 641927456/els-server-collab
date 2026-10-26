# OWNED_QA_CLEANUP_V1
import types as _qa_types
_qa_cleanup = _qa_types.ModuleType("owned_qa_cleanup")
exec(compile('"""Owned QA authentication lifecycle. Never opens the game database writable.\n\nEnrollment is durable before allocation commits. Cleanup is limited to those\nexact IDs and token hashes, requires a live writer barrier, and retains one\nshared ID watermark because the existing allocator uses MAX(id)+1.\n"""\nfrom contextlib import closing\nfrom pathlib import Path\nimport hashlib\nimport json\nimport os\nimport re\nimport secrets\nimport sqlite3\nimport time\n\n\nclass CleanupError(RuntimeError):\n    pass\n\n\ndef require(value, message):\n    if not value:\n        raise CleanupError(message)\n\n\ndef read(path):\n    return json.loads(Path(path).read_text(encoding=\'utf8\'))\n\n\ndef write(path, value):\n    path = Path(path)\n    path.parent.mkdir(parents=True, exist_ok=True)\n    tmp = path.with_name(path.name + \'.next\')\n    with tmp.open(\'w\', encoding=\'utf8\') as stream:\n        json.dump(value, stream, ensure_ascii=False, indent=2)\n        stream.write(\'\\n\')\n        stream.flush()\n        os.fsync(stream.fileno())\n    os.replace(tmp, path)\n\n\ndef ro(path):\n    db = sqlite3.connect(Path(path).resolve().as_uri() + \'?mode=ro\', uri=True, timeout=30)\n    db.execute(\'PRAGMA query_only=ON\')\n    return db\n\n\ndef fingerprint(value):\n    return hashlib.sha256(repr(value).encode()).hexdigest()\n\n\ndef create_owned_account(accounts_file, work, name, operation, *, allocation_key=\'a\'):\n    """Use the native schema/allocator, with proof persisted before COMMIT."""\n    require(bool(re.fullmatch(r\'[a-z][a-z0-9_]{2,23}\', name)), \'Invalid QA name\')\n    path = Path(work) / \'owned-account-enrollment.private.json\'\n    token = secrets.token_urlsafe(32)\n    token_hash = hashlib.sha256(token.encode()).hexdigest()\n    with closing(sqlite3.connect(accounts_file, timeout=30)) as db, db:\n        db.execute(\'BEGIN IMMEDIATE\')\n        if path.exists():\n            document=read(path)\n            require(document[\'operation\']==operation and\n                    document[\'accounts_file\']==str(Path(accounts_file).resolve()),\'Enrollment binding mismatch\')\n            require(all(t.get(\'allocation_key\',\'a\')!=allocation_key for t in document[\'targets\']),\n                    \'Enrollment already exists; do not allocate twice\')\n        else:\n            document=dict(version=1, operation=operation,\n                          accounts_file=str(Path(accounts_file).resolve()),targets=[])\n        identity = db.execute(\'SELECT COALESCE(MAX(id),1)+1 FROM accounts\').fetchone()[0]\n        document[\'targets\'].append(dict(id=identity,name=name,token_hash=token_hash,allocation_key=allocation_key))\n        write(path, document)\n        db.execute(\'INSERT INTO accounts VALUES (?,?,?,1)\', (identity, name, token_hash))\n    return dict(id=identity, name=name, token=token)\n\n\ndef backup(source, target):\n    target = Path(target)\n    if not target.exists():\n        with closing(ro(source)) as src, closing(sqlite3.connect(target)) as dst:\n            src.backup(dst)\n    with closing(ro(target)) as db:\n        require(db.execute(\'PRAGMA quick_check\').fetchall() == [(\'ok\',)], \'Backup invalid\')\n    return dict(path=str(target), sqlite_backup_API=True, quick_check=\'ok\')\n\n\ndef schema(db):\n    return db.execute(\'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name\').fetchall()\n\n\ndef protected_rows(db, excluded):\n    marks = \',\'.join(\'?\' for _ in excluded)\n    return {table: fingerprint(db.execute(\n        \'SELECT * FROM \' + table + \' WHERE \' + key + \' NOT IN (\' + marks + \') ORDER BY rowid\',\n        tuple(excluded)).fetchall())\n        for table, key in ((\'accounts\', \'id\'), (\'account_passwords\', \'account_id\'),\n                           (\'account_sessions\', \'account_id\'))}\n\n\ndef validate_target(db, target, *, may_be_absent=False):\n    row = db.execute(\'SELECT id,name,token_hash,enabled FROM accounts WHERE id=?\',\n                     (target[\'id\'],)).fetchone()\n    if row is None and may_be_absent:\n        return None\n    require(row is not None and tuple(row[:3]) == (\n        target[\'id\'], target[\'name\'], target[\'token_hash\']), \'QA identity or credentials changed\')\n    # These scripts allocate token-only QA. A later password means ownership\n    # changed or another workflow touched it, so preserve the account.\n    require(db.execute(\'SELECT 1 FROM account_passwords WHERE account_id=?\',\n                       (target[\'id\'],)).fetchone() is None, \'QA acquired a password; preserve it\')\n    return row\n\n\ndef cleanup_owned_accounts(accounts_file, game_file, work, operation, *, capacity,\n                           barrier, lease_check, fault=None):\n    """Idempotent end-of-test cleanup; caller closes peers before entering.\n\n    barrier(ids) must enter the real serialized application and check completed\n    authenticated connections. lease_check must verify the publication owner.\n    Neither callback is supplied by a network request or normal player action.\n    """\n    work = Path(work).resolve()\n    enrollment_file = work / \'owned-account-enrollment.private.json\'\n    require(enrollment_file.is_file(), \'No durable own-account enrollment; preserve all accounts\')\n    proof = read(enrollment_file)\n    require(proof[\'version\'] == 1 and proof[\'operation\'] == operation and\n            proof[\'accounts_file\'] == str(Path(accounts_file).resolve()), \'Enrollment binding mismatch\')\n    targets = proof[\'targets\']\n    ids = tuple(t[\'id\'] for t in targets)\n    require(ids and len(set(ids)) == len(ids) and all(type(i) is int and i >= 2 for i in ids),\n            \'Invalid enrolled IDs\')\n    lease_check()\n    coordination = Path(accounts_file).resolve().parent / \'owned-qa-cleanup\'\n    coordination.mkdir(exist_ok=True)\n    lock = coordination / \'cleanup.lock\'\n    identity = dict(operation=operation, token=secrets.token_hex(16), pid=os.getpid())\n    try:\n        with lock.open(\'x\', encoding=\'utf8\') as stream:\n            json.dump(identity, stream)\n    except FileExistsError as exc:\n        write(work / \'account-cleanup-pending.json\', dict(operation=operation,\n              reason=\'Another owned QA cleanup holds the lock\', ids=list(ids)))\n        raise CleanupError(\'Owned QA cleanup busy; pending receipt retained\') from exc\n    try:\n        return _cleanup(accounts_file, game_file, work, proof, capacity, barrier,\n                        lease_check, coordination, fault)\n    except BaseException as exc:\n        write(work / \'account-cleanup-pending.json\', dict(operation=operation,\n              reason=type(exc).__name__ + \': \' + str(exc), ids=list(ids)))\n        raise\n    finally:\n        if lock.exists() and read(lock) == identity:\n            lock.unlink()\n\n\ndef _cleanup(accounts_file, game_file, work, proof, capacity, barrier, lease_check,\n             coordination, fault):\n    targets = proof[\'targets\']; ids = tuple(t[\'id\'] for t in targets)\n    operation = proof[\'operation\']; marks = \',\'.join(\'?\' for _ in ids)\n    receipt = work / \'account-cleanup.json\'\n    journal_file = work / \'account-cleanup-transaction.json\'\n    watermark_file = coordination / \'watermark.json\'\n    if receipt.exists():\n        previous = read(receipt)\n        require(previous[\'operation\'] == operation and previous[\'ok\'], \'Cleanup receipt binding changed\')\n        lease_check()\n        require(barrier(ids) is True, \'Repeated cleanup writer barrier unresolved\')\n        with closing(ro(accounts_file)) as db:\n            current_guard = read(watermark_file) if watermark_file.exists() else None\n            for target in targets:\n                if target[\'id\'] not in previous.get(\'cleaned_account_ids\',[]):continue\n                row = db.execute(\'SELECT * FROM accounts WHERE id=?\', (target[\'id\'],)).fetchone()\n                require(row is None or (current_guard and row[0] == current_guard[\'id\'] and\n                        fingerprint(row) == current_guard[\'row_sha256\']), \'Retired QA was recreated\')\n            require(previous.get(\'no_allocation\') or db.execute(\'SELECT COALESCE(MAX(id),1) FROM accounts\').fetchone()[0] >= max(previous[\'cleaned_account_ids\']),\n                    \'Account ID boundary lost\')\n        return previous\n    if journal_file.exists():\n        journal = read(journal_file)\n        require(journal[\'operation\'] == operation, \'Cleanup journal binding mismatch\')\n        with closing(ro(accounts_file)) as db:\n            state = _transaction_state(db, journal)\n        if state == \'committed\':\n            # Lost response / process exit after COMMIT: recover metadata only.\n            return _finish(accounts_file, work, journal, watermark_file, receipt, barrier, lease_check)\n        require(state == \'not-committed\', \'Ambiguous cleanup outcome; preserve all records\')\n    else:\n        journal = None\n    backups = dict(accounts=backup(accounts_file, work / \'accounts-before-cleanup.sqlite3\'),\n                   game=backup(game_file, work / \'game-before-cleanup.sqlite3\'))\n    with closing(sqlite3.connect(accounts_file, timeout=30)) as db, db:\n        db.execute(\'BEGIN IMMEDIATE\')\n        require({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type=\'table\'")} ==\n                {\'accounts\', \'account_passwords\', \'account_sessions\'} and\n                not db.execute("SELECT 1 FROM sqlite_master WHERE type=\'trigger\'").fetchone(),\n                \'Unreviewed authentication schema or triggers\')\n        for target in targets:\n            row = validate_target(db, target, may_be_absent=True)\n            if row is None:\n                # Durable enrollment may precede a rolled back allocation.\n                continue\n            db.execute(\'UPDATE accounts SET enabled=0 WHERE id=?\', (target[\'id\'],))\n    lease_check()\n    require(barrier(ids) is True, \'Own QA writer barrier unresolved\')\n    with closing(ro(game_file)) as game:\n        owner_rows = game.execute(\'SELECT uid,account_id FROM character_owners WHERE account_id IN (\' +\n                                  marks + \') ORDER BY uid\', ids).fetchall()\n    with closing(sqlite3.connect(accounts_file, timeout=30, isolation_level=None)) as db:\n        db.execute(\'PRAGMA foreign_keys=ON\')\n        db.execute(\'BEGIN IMMEDIATE\')\n        try:\n            require({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type=\'table\'")} ==\n                    {\'accounts\', \'account_passwords\', \'account_sessions\'}, \'Unreviewed authentication schema\')\n            old_schema = schema(db)\n            present = []\n            for target in targets:\n                row = validate_target(db, target, may_be_absent=True)\n                if row is not None:\n                    require(row[3] == 0, \'QA was re-enabled\')\n                    present.append(target)\n            if not present:\n                db.execute(\'ROLLBACK\')\n                result = dict(ok=True, operation=operation, no_allocation=True,\n                    cleaned_account_ids=[], deleted_ids=[], slots_freed=0,\n                    capacity_delta_verified=True, protected_authentication_rows_preserved=True,\n                    game_database_modified=False, writer_barrier_passed=True, backups=backups)\n                write(receipt, result)\n                return result\n            previous_guard = read(watermark_file) if watermark_file.exists() else None\n            if previous_guard is not None:\n                guard_row = db.execute(\'SELECT * FROM accounts WHERE id=?\', (previous_guard[\'id\'],)).fetchone()\n                require(guard_row and fingerprint(guard_row) == previous_guard[\'row_sha256\'] and\n                        guard_row[1] == \'retired_qa_id_guard\' and guard_row[3] == 0,\n                        \'Shared watermark changed; do not guess or delete it\')\n                require(db.execute(\'SELECT 1 FROM account_passwords WHERE account_id=?\',\n                                   (guard_row[0],)).fetchone() is None and\n                        db.execute(\'SELECT 1 FROM account_sessions WHERE account_id=?\',\n                                   (guard_row[0],)).fetchone() is None, \'Watermark acquired credentials\')\n            else:\n                require(not db.execute("SELECT 1 FROM accounts WHERE name=\'retired_qa_id_guard\'").fetchone(),\n                        \'Unproven watermark name collision\')\n            maximum = db.execute(\'SELECT COALESCE(MAX(id),1) FROM accounts\').fetchone()[0]\n            before = db.execute(\'SELECT COUNT(*) FROM accounts\').fetchone()[0]\n            guard_id = maximum if maximum in {t[\'id\'] for t in present} else None\n            exclusions = {t[\'id\'] for t in present}\n            if previous_guard:\n                exclusions.add(previous_guard[\'id\'])\n            require(exclusions, \'No committed allocation to clean\')\n            preserved = protected_rows(db, exclusions)\n            enabled = db.execute(\'SELECT COUNT(*) FROM accounts WHERE enabled=1\').fetchone()[0]\n            deleted = [t[\'id\'] for t in present if t[\'id\'] != guard_id]\n            if previous_guard and (guard_id is not None or previous_guard[\'id\'] < maximum):\n                deleted.append(previous_guard[\'id\'])\n            new_guard = previous_guard\n            if guard_id is not None:\n                if previous_guard:\n                    db.execute(\'DELETE FROM accounts WHERE id=?\', (previous_guard[\'id\'],))\n                db.execute(\'UPDATE accounts SET name=?,token_hash=?,enabled=0 WHERE id=?\',\n                           (\'retired_qa_id_guard\', hashlib.sha256(secrets.token_bytes(32)).hexdigest(), guard_id))\n                row = db.execute(\'SELECT * FROM accounts WHERE id=?\', (guard_id,)).fetchone()\n                new_guard = dict(id=guard_id, row_sha256=fingerprint(row), operation=operation)\n            elif previous_guard and previous_guard[\'id\'] < maximum:\n                db.execute(\'DELETE FROM accounts WHERE id=?\', (previous_guard[\'id\'],))\n                new_guard = None\n            for target in present:\n                db.execute(\'DELETE FROM account_sessions WHERE account_id=?\', (target[\'id\'],))\n                if target[\'id\'] != guard_id:\n                    db.execute(\'DELETE FROM accounts WHERE id=? AND enabled=0\', (target[\'id\'],))\n            require(protected_rows(db, exclusions) == preserved, \'Protected authentication row changed\')\n            require(schema(db) == old_schema, \'Authentication schema changed\')\n            require(db.execute(\'PRAGMA foreign_key_check\').fetchall() == [], \'Authentication FK check failed\')\n            require(db.execute(\'PRAGMA quick_check\').fetchall() == [(\'ok\',)], \'Authentication integrity failed\')\n            require(db.execute(\'SELECT COUNT(*) FROM accounts WHERE enabled=1\').fetchone()[0] == enabled,\n                    \'Enabled player count changed\')\n            require(db.execute(\'SELECT COALESCE(MAX(id),1) FROM accounts\').fetchone()[0] >= maximum,\n                    \'Account IDs could be recycled\')\n            after = db.execute(\'SELECT COUNT(*) FROM accounts\').fetchone()[0]\n            require(before - after == len(deleted), \'Registration capacity delta mismatch\')\n            journal = dict(operation=operation, phase=\'prepared\', ids=list(ids),\n                targets=present, deleted_ids=deleted, watermark=new_guard, accounts_before=before,\n                accounts_after=after, slots_freed=before-after, capacity=capacity,\n                available_registration_slots=max(0, capacity-after), backups=backups,\n                protected_rows=preserved, exclusions=sorted(exclusions),\n                game_owner_rows=[list(r) for r in owner_rows], game_database_modified=False)\n            write(journal_file, journal)\n            lease_check()\n            if fault: fault(\'before_commit\')\n            db.execute(\'COMMIT\')\n            if fault: fault(\'after_commit\')\n        except BaseException:\n            if db.in_transaction: db.execute(\'ROLLBACK\')\n            raise\n    with closing(ro(game_file)) as game:\n        require([list(r) for r in game.execute(\'SELECT uid,account_id FROM character_owners WHERE account_id IN (\'+\n                marks+\') ORDER BY uid\', ids)] == journal[\'game_owner_rows\'], \'QA game ownership changed\')\n    return _finish(accounts_file, work, journal, watermark_file, receipt, barrier, lease_check)\n\n\ndef _transaction_state(db, journal):\n    require(journal[\'phase\'] == \'prepared\', \'Unknown cleanup journal phase\')\n    deleted_absent = all(db.execute(\'SELECT 1 FROM accounts WHERE id=?\', (i,)).fetchone() is None\n                         for i in journal[\'deleted_ids\'])\n    guard = journal[\'watermark\']\n    guard_matches = not guard or fingerprint(db.execute(\'SELECT * FROM accounts WHERE id=?\',\n                                                      (guard[\'id\'],)).fetchone()) == guard[\'row_sha256\']\n    if deleted_absent and guard_matches:\n        return \'committed\'\n    originals = all(validate_target(db, t, may_be_absent=False) for t in journal[\'targets\'])\n    return \'not-committed\' if originals else \'ambiguous\'\n\n\ndef _finish(accounts_file, work, journal, watermark_file, receipt, barrier, lease_check):\n    lease_check()\n    require(barrier(tuple(journal[\'ids\'])) is True, \'Final QA writer barrier unresolved\')\n    with closing(ro(accounts_file)) as db:\n        require(_transaction_state(db, journal) == \'committed\', \'Cleanup did not commit\')\n        total = db.execute(\'SELECT COUNT(*) FROM accounts\').fetchone()[0]\n        # Check targets rather than global row hashes after releasing the auth\n        # transaction: legitimate player logins/registrations may now proceed.\n    if journal[\'watermark\']:\n        write(watermark_file, journal[\'watermark\'])\n    elif watermark_file.exists():\n        watermark_file.unlink()\n    result = dict(ok=True, operation=journal[\'operation\'],\n        cleaned_account_ids=[t[\'id\']for t in journal[\'targets\']], deleted_ids=journal[\'deleted_ids\'],\n        shared_watermark_id=journal[\'watermark\'][\'id\'] if journal[\'watermark\'] else None,\n        shared_watermark_records=1 if journal[\'watermark\'] else 0,\n        accounts_before=journal[\'accounts_before\'], accounts_after=journal[\'accounts_after\'],\n        slots_freed=journal[\'slots_freed\'], current_accounts=total,\n        available_registration_slots=max(0, journal[\'capacity\']-total),\n        capacity_delta_verified=True, protected_authentication_rows_preserved=True,\n        game_database_modified=False, writer_barrier_passed=True, backups=journal[\'backups\'])\n    write(receipt, result)\n    pending = Path(work) / \'account-cleanup-pending.json\'\n    if pending.exists(): pending.unlink()\n    return result\n', "owned_qa_cleanup.py", "exec"), _qa_cleanup.__dict__)
"""Once-only new own QA role; snapshots are read-only, terminal only disables it."""
from pathlib import Path
from contextlib import closing
import argparse,hashlib,json,os,sqlite3,ssl,sys,time,traceback,urllib.request
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
 p=Path(p);tmp=p.with_suffix('.next');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8');os.replace(tmp,p)
def execute(cfg,action):
 root=Path(cfg['root']).resolve();work=Path(cfg['work']).resolve();assert work.is_relative_to(root/'backups'/cfg['release'])and work.name=='public-QA-'+cfg['operation']
 if action=='setup':work.mkdir(parents=True,exist_ok=False)
 dest=work/(action+'-result.json')
 if dest.exists():return read(dest)
 with(work/(action+'-claim.json')).open('x',encoding='utf8')as f:json.dump(dict(action=action,pid=os.getpid(),automatic_retry=False),f);f.flush();os.fsync(f.fileno())
 result=dict(ok=False,action=action,release=cfg['release']);state_path=work/'state.private.json'
 try:
  if not cfg.get('private',False):
   assert root==Path('C:/ElsFriends').resolve()
   assert sha(root/('release-'+cfg['release']+'.json'))==cfg['manifest_sha256']
   journal=read(Path(cfg['stage'])/'journal.json');assert journal['phase']=='awaiting-public-acceptance'and journal['observation_seconds']>=120
   for rel,h in cfg['expected_leaves'].items():assert sha(root/rel)==h
  sys.path.insert(0,str(root));sys.dont_write_bytecode=True
  from els_server.config import ServerConfig
  c=ServerConfig.load(cfg['config'])
  from els_server.domain.activity_2026_rewards import ActivityRewards
  import els_server.domain.activity_2026_rewards as activity_source
  ActivityRewards((Path(activity_source.__file__).resolve().parents[1]/'data/selected2026/rewards.json').read_bytes()).register_inventory()
  from els_server.domain.boosting_2026_participation_gear import register as register_gear
  register_gear()
  from els_server.storage.accounts import Accounts
  from els_server.storage.characters import Characters
  from els_server.storage.inventory_state import grant_items,load_items
  def status():
   if cfg.get('private',False):return dict(ready=True,owned=True,phase='running',players=[])
   key=(root/'state/gm/access.key').read_text('ascii').strip()
   return json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18765/api/status',headers={'X-GM-Key':key}),timeout=10))['result']
  if action=='setup':
   name='qa_ns_'+cfg['operation'][:12]
   with closing(sqlite3.connect(c.accounts_file.as_uri()+'?mode=ro',uri=True))as db:
    assert not db.execute('SELECT 1 FROM accounts WHERE name=?',(name,)).fetchone();amax=db.execute('SELECT coalesce(max(id),1) FROM accounts').fetchone()[0]
   with closing(sqlite3.connect(c.state_file.as_uri()+'?mode=ro',uri=True))as db:
    assert db.execute('SELECT count(*) FROM characters c LEFT JOIN character_owners o ON c.uid=o.uid WHERE o.uid IS NULL').fetchone()==(0,)
    umax=db.execute('SELECT coalesce(max(uid),1001) FROM characters').fetchone()[0]
   state=dict(operation=cfg['operation'],previous_max_account=amax,previous_max_uid=umax,planned_names={'a':name},accounts={},roles={},planned_roles={'gear':dict(name='NS'+cfg['operation'][:8],operation='own-public-native-stats:'+cfg['operation'])},initial_items={},phase='before-allocation');write(state_path,state)
   state['accounts']['a']=_qa_cleanup.create_owned_account(c.accounts_file, work, name, cfg['operation']);write(state_path,state);a=state['accounts']['a']
   roster=Characters.__new__(Characters);roster.path=c.state_file;roster.account_id=a['id'];assert roster.list()==[]
   r=roster.create(state['planned_roles']['gear']['name'],1,state['planned_roles']['gear']['operation']);assert r['uid']>max(1001,umax)and r['level']==1
   state['roles']['gear']=dict(uid=r['uid'],name=r['name'],account='a');write(state_path,state)
   with closing(sqlite3.connect(c.state_file))as db,db:
    db.execute('BEGIN IMMEDIATE');assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(r['uid'],)).fetchone()==(a['id'],)
    state['initial_items']['gear']=load_items(db,r['uid'])
    # Explicit fixture on the newly allocated own role only, before login.
    state['fixtures']=[]
    db.execute('UPDATE characters SET level=99 WHERE uid=?',(r['uid'],))
   from els_server.storage.inventory_state import grant_items
   from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
   with closing(sqlite3.connect(c.state_file))as db,db:
    db.execute('BEGIN IMMEDIATE');assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(r['uid'],)).fetchone()==(a['id'],)
    state['fixtures']=grant_items(db,[dict(template=723680,metadata=VERIFIED_TEMPLATES[723680],group=TEMPLATE_BAG_GROUPS[723680],quantity=1)],r['uid'])
   state['phase']='normal-own-role-with-explicit-fixtures';write(state_path,state)
   pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(c.tls_cert.read_text('ascii'))).hexdigest()
   write(work/'credentials.private.json',dict(account=a,uid=r['uid'],pin=pin))
   result.update(ok=True,account_id=a['id'],uid=r['uid'],accounts_created=1,characters_created=1,fixture_items=[dict(template=i['template'],uid=i['uid'],count=i['count'])for i in state['fixtures']],fixture_not_natural_source=True,level=99,ED_writes=0)
  else:
   state=read(state_path);assert state['operation']==cfg['operation'];a=state['accounts'].get('a');uid=state['roles'].get('gear',{}).get('uid')
   with closing(sqlite3.connect(c.accounts_file.as_uri()+'?mode=ro',uri=True))as db:
    if a is None:
     assert action=='terminal';row=db.execute('SELECT id,name FROM accounts WHERE name=?',(state['planned_names']['a'],)).fetchone();assert row and row[0]>state['previous_max_account'];a=dict(id=row[0],name=row[1])
    else:assert db.execute('SELECT name,token_hash FROM accounts WHERE id=?',(a['id'],)).fetchone()==(a['name'],hashlib.sha256(a['token'].encode()).hexdigest())
   if action in('close','terminal'):
    if action=='terminal':
     with closing(sqlite3.connect(c.accounts_file,timeout=10))as db,db:
      db.execute('BEGIN IMMEDIATE');assert db.execute('UPDATE accounts SET enabled=0 WHERE id=? AND name=?',(a['id'],a['name'])).rowcount==1
    # API status enters the actual serialized application after all packets;
    # the owned authenticated connections must also have finished in the log.
    end=time.monotonic()+25
    while True:
     live=status();active=[]
     if not cfg.get('private',False):
      authenticated=set();finished=set()
      for p in c.log_dir.glob('server.jsonl*'):
       for line in p.read_text('utf8').splitlines():
        e=json.loads(line)
        if e.get('event')=='authenticated'and e.get('account_id')==a['id']:authenticated.add(e['connection'])
        if e.get('event')=='connection_finished':finished.add(e['connection'])
      active=sorted(authenticated-finished)
     if not active and not any(p.get('uid')==uid or p.get('account_id')==a['id']for p in live.get('players',[])):break
     assert time.monotonic()<end,'Own QA release/writer barrier unresolved';time.sleep(.25)
    assert live['ready']and live['owned']and live['phase']=='running';result.update(ok=True,writer_barrier_passed=True,no_active=True,disabled=action=='terminal',account_id=a['id'],uid=uid)
    if action=='terminal':
     for p in(work/'credentials.private.json',state_path):
      assert p.resolve().parent==work and p.is_file();p.unlink()
     result['remote_credentials_removed']=True
   else:
    with closing(sqlite3.connect(c.state_file.as_uri()+'?mode=ro',uri=True))as db:
     db.execute('PRAGMA query_only=ON');db.execute('BEGIN');assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(a['id'],)
     result.update(ok=True,uid=uid,account_id=a['id'],readonly=True,action_receipts=db.execute('SELECT operation_id,kind FROM inventory_action_receipts WHERE owner=? ORDER BY operation_id',(uid,)).fetchall()if db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone()else[],wear_receipts=db.execute('SELECT operation_id,positions_json FROM wear_move_receipts WHERE owner=? ORDER BY operation_id',(uid,)).fetchall()if db.execute("SELECT 1 FROM sqlite_master WHERE name='wear_move_receipts'").fetchone()else[],location=db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(uid,)).fetchone(),warp_receipts=[dict(operation=op,grant=json.loads(g))for op,g in db.execute("SELECT run_id,grant_json FROM reward_receipts WHERE grant_json LIKE '%town_warp%'")if json.loads(g).get('owner')==uid],level=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()[0],items=load_items(db,uid),balances=db.execute('SELECT * FROM reward_balances WHERE uid=?',(uid,)).fetchall(),cooldowns=db.execute('SELECT cooldown_group,ready_at FROM consumable_cooldowns WHERE owner=?',(uid,)).fetchall()if db.execute("SELECT 1 FROM sqlite_master WHERE name='consumable_cooldowns'").fetchone()else[],quick_uses=db.execute('SELECT template,item_uid FROM consumable_uses WHERE owner=?',(uid,)).fetchall()if db.execute("SELECT 1 FROM sqlite_master WHERE name='consumable_uses'").fetchone()else[],world=db.execute('SELECT revision,template,source_uid,starts_at,ends_at FROM world_elixir_state WHERE owner=?',(uid,)).fetchall()if db.execute("SELECT 1 FROM sqlite_master WHERE name='world_elixir_state'").fetchone()else[])
 except BaseException:result['error']=traceback.format_exc();raise
 finally:write(dest,result)
 return result

_qa_native_execute = execute
def _qa_cleanup_config(cfg, ids):
 root=Path(cfg['root']).resolve();work=Path(cfg['work']).resolve()
 _qa_cleanup.require(work.is_relative_to(root/'backups'/cfg['release']) and work.name=='public-QA-'+cfg['operation'], 'QA work binding changed')
 from els_server.config import ServerConfig
 c=ServerConfig.load(cfg['config'])
 def lease():
  if cfg.get('private',False):return
  own=cfg.get('cleanup_lease',{})
  _qa_cleanup.require(bool(own.get('token')) and own.get('release')==cfg['release'], 'Publication cleanup lease missing')
  _qa_cleanup.require(root==Path('C:/ElsFriends').resolve() and sha(root/('release-'+cfg['release']+'.json'))==cfg['manifest_sha256'], 'QA release changed')
  j=read(Path(cfg['stage'])/'journal.json')
  _qa_cleanup.require(j['phase']=='awaiting-public-acceptance' and j['observation_seconds']>=120, 'Publication phase changed')
  for rel,h in cfg['expected_leaves'].items():_qa_cleanup.require(sha(root/rel)==h,'Runtime changed')
 def barrier(targets):
  if cfg.get('private',False):
   # The private public_qa harness drains server.connections and app.call
   # before terminal; SQL tests exercise this callback separately.
   return cfg.get('cleanup_private_barrier_passed') is True
  key=(root/'state/gm/access.key').read_text('ascii').strip()
  live=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18765/api/status',headers={'X-GM-Key':key}),timeout=10))['result']
  authenticated=set();finished=set()
  for p in c.log_dir.glob('server.jsonl*'):
   for line in p.read_text('utf8').splitlines():
    e=json.loads(line)
    if e.get('event')=='authenticated' and e.get('account_id')in targets:authenticated.add(e['connection'])
    if e.get('event')=='connection_finished':finished.add(e['connection'])
  with closing(_qa_cleanup.ro(c.state_file))as db:
   owners={r[0]for r in db.execute('SELECT uid FROM character_owners WHERE account_id IN ('+','.join('?'for _ in targets)+')',tuple(targets))}
  return live['ready'] and live['owned'] and live['phase']=='running' and not(authenticated-finished) and not any(p.get('account_id')in targets or p.get('uid')in owners for p in live.get('players',[]))
 return _qa_cleanup.cleanup_owned_accounts(c.accounts_file,c.state_file,work,cfg['operation'],capacity=c.max_registered_accounts,barrier=barrier,lease_check=lease)

def execute(cfg,action):
 if action!='terminal':return _qa_native_execute(cfg,action)
 work=Path(cfg['work']);dest=work/'terminal-result.json'
 native=None;native_error=None
 try:native=_qa_native_execute(cfg,action)
 except BaseException as exc:native_error=exc
 try:
  enrollment=work/'owned-account-enrollment.private.json'
  if enrollment.exists():
   cleanup=_qa_cleanup_config(cfg,())
  else:
   # No enrolled INSERT was attempted by this integrated worker.
   cleanup=dict(ok=True,no_allocation=True,capacity_delta_verified=True,slots_freed=0)
  if native_error is not None:raise native_error
  native=dict(native)
  if native.get('native_terminal_ok'):native['ok']=True
  native.pop('account_cleanup_pending',None)
  if 'cleanup_error'in native:native['previous_cleanup_error']=native.pop('cleanup_error')
  native.update(account_cleanup=cleanup,own_accounts_cleaned=True,registration_capacity_verified=cleanup['capacity_delta_verified'])
  write(dest,native)
  return native
 except BaseException:
  failure=dict(native or {},ok=False,native_terminal_ok=bool(native and(native.get('ok')or native.get('native_terminal_ok'))),account_cleanup_pending=True,cleanup_error=traceback.format_exc())
  write(dest,failure)
  raise

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--action',required=True);a=p.parse_args();execute(read(a.config),a.action)
