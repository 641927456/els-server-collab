"""Index migration remains atomic and creates one index on an empty store."""
import runtime_fixture as h
import asyncio,contextlib,json,sqlite3
from profile_town import seed
from els_server.storage.online_2026_progress import OnlineTitleProgress as Original
proposal=h.load('own_cover_atomic',h.H/'experiments/online-span-covering-v2/online_2026_progress.py')
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();checks=[]
 try:
  uid=seed(c,c.alice,'OwnIxAtomic',False);p=await c.peer(c.alice);await p.roster();await p.enter_town(uid);await c.server.periodics.close();clock=c.app.playing[c.alice['id']].activity2026_awards.online.title.clock
  for case in('fresh','bad_definition'):
   path=c.root/(case+'.sqlite3')
   with contextlib.closing(sqlite3.connect(path))as db:
    if case=='bad_definition':
     old=Original(db,clock.selection_bytes,campaign=clock.campaign)
     with db:db.execute('BEGIN IMMEDIATE');old.initialize();db.execute('UPDATE online2026_campaigns SET definition_sha256=?',('0'*64,))
    before=db.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
    repo=proposal.OnlineTitleProgress(db,clock.selection_bytes,campaign=clock.campaign)
    with db:
     db.execute('BEGIN IMMEDIATE')
     try:repo.initialize()
     except ValueError:
      assert case=='bad_definition'
      # Commit the outer transaction: only the initializer's own savepoint
      # can restore its CREATE/DROP if validation fails after migration.
     else:assert case=='fresh'
    if case=='bad_definition':assert db.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()==before
    else:
     rows=db.execute("SELECT name FROM sqlite_master WHERE type='index'AND tbl_name='online2026_spans'AND sql IS NOT NULL").fetchall()
     assert rows==[('online2026_character_account_spans',)]
     assert [r[2]for r in db.execute('PRAGMA index_info(online2026_character_account_spans)')]==['campaign','character','account','week','starts','ends']
    checks.append(case)
 finally:await c.asyncTearDown()
 out=dict(passed=True,proposal_only=True,checks=checks,owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
 (h.H/'online-span-index-atomic-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
