"""Only new saved-lifecycle, receipt, legacy and internal-cleanup risks."""
import ast,hashlib,json,sqlite3,sys,tempfile,time,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
sys.dont_write_bytecode=True
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.storage import game_mail,player_mail,mailbox_extras
from els_server.storage.character_selection import save
from els_server.storage.character_lifecycle import change,DAY
ROWS=[]

class Guard(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='mail-actor-private-');self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'game.sqlite3';self.now=int(time.time())
  self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();game_mail.initialize(self.path)
  self.target=Characters(self.path,2).create('TargetActor',1,'target-actor')['uid']
  self.req=dict(recipient='TargetActor',title='Private state combo',body='No real mail',ed=25,item=0,count=0,flag=0,extra=0)
  with closing(sqlite3.connect(self.path)) as db,db:
   db.execute('UPDATE reward_balances SET ed=10000 WHERE uid=1001')
   for mid,amount in [(101,0),(102,500),(103,0),(104,500),(105,0),(106,0)]:
    db.execute('INSERT INTO game_mail(id,campaign,account_id,sender,title,body,ed,created_at,expires_at) VALUES (?,?,1,?,?,?,?,?,?)',(mid,'private-'+str(mid),'Synthetic','Private','New lifecycle only',amount,self.now-100,self.now+3600))
  save(self.path,1,[],[1001])
 def dump(self):
  with closing(sqlite3.connect(self.path)) as db:return tuple(db.iterdump())
 def schedule(self,when):
  with patch('els_server.storage.character_lifecycle.current_time',return_value=when):return change(self.path,1,1001,'schedule')
 def send(self,op):return player_mail.send(self.path,1,1001,self.req,op,lambda row:row)
 def block(self,added,op):return mailbox_extras.change(self.path,1,1001,'TargetActor' if added else self.target,added=added,operation=op,encode=lambda row,result,rows:(row,result,rows))
 def test_pending_restored_finalized_new_and_committed(self):
  self.send('committed-send');game_mail.read(self.path,1,1001,101,lambda r:r);game_mail.claim(self.path,1,1001,[102],lambda ids,ed:(ids,ed));game_mail.delete(self.path,1,1001,[103],lambda ids:ids)
  self.block(True,'committed-add');self.block(False,'committed-remove')
  actions=[('send-new',lambda:self.send('new-send')),('send-old-receipt',lambda:self.send('committed-send')),('read-new',lambda:game_mail.read(self.path,1,1001,105,lambda r:r)),('read-already-read',lambda:game_mail.read(self.path,1,1001,101,lambda r:r)),('claim-new',lambda:game_mail.claim(self.path,1,1001,[104],lambda ids,ed:(ids,ed))),('claim-old',lambda:game_mail.claim(self.path,1,1001,[102],lambda ids,ed:(ids,ed))),('delete-new',lambda:game_mail.delete(self.path,1,1001,[106],lambda ids:ids)),('delete-old',lambda:game_mail.delete(self.path,1,1001,[103],lambda ids:ids)),('block-add-new',lambda:self.block(True,'new-add')),('block-add-old-receipt',lambda:self.block(True,'committed-add')),('block-remove-new',lambda:self.block(False,'new-remove')),('block-remove-old-receipt',lambda:self.block(False,'committed-remove'))]
  self.schedule(self.now)
  for stage in ['pending','finalized']:
   if stage=='finalized':
    with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now+DAY+1):change(self.path,1,1001,'restore')
    old=[('send',lambda:self.send('committed-send')),('read',lambda:game_mail.read(self.path,1,1001,101,lambda r:r)),('claim',lambda:game_mail.claim(self.path,1,1001,[102],lambda ids,ed:(ids,ed))),('delete',lambda:game_mail.delete(self.path,1,1001,[103],lambda ids:ids)),('blockadd',lambda:self.block(True,'committed-add')),('blockremove',lambda:self.block(False,'committed-remove'))]
    for label,fn in old:
     before=self.dump();fn();self.assertEqual(self.dump(),before);ROWS.append(dict(stage='restored-committed-no-duplicate',label=label,passed=True))
    cold=LocalAccount(LocalState(self.path));cold.enable_characters()
    with closing(sqlite3.connect(self.path)) as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
    ROWS.append(dict(stage='cold-state-open-FK-clean',passed=True))
    self.schedule(self.now+2*DAY+2)
    with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now+5*DAY+3):change(self.path,1,1001,'finalize')
   for label,fn in actions:
    before=self.dump()
    with self.assertRaisesRegex(game_mail.MailError,'Mail character is pending deletion or finalized') as error:fn()
    self.assertEqual(error.exception.code,1);self.assertEqual(self.dump(),before)
    ROWS.append(dict(stage=stage,label=label,MailError=1,SQL_unchanged=True))
 def test_queries_expiry_legacy_and_transaction_boundary(self):
  outbound=self.send('internal-expiry-source')['mail_id'];self.schedule(self.now)
  for label,fn in [('inbox',lambda:game_mail.inbox(self.path,1,1001)),('status',lambda:mailbox_extras.status(self.path,1,1001)),('blacklist',lambda:mailbox_extras.blacklist(self.path,1,1001))]:
   before=self.dump();fn();self.assertEqual(before,self.dump());ROWS.append(dict(stage='pending-read-only-compatible',label=label,SQL_unchanged=True))
  with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE game_mail SET expires_at=? WHERE id=?',(self.now-1,outbound))
  self.assertEqual(player_mail.maintenance(self.path,now=self.now),1)
  with closing(sqlite3.connect(self.path)) as db:
   returned=db.execute('SELECT g.account_id,g.ed,p.recipient_uid,p.return_of FROM game_mail g JOIN player_mail_meta p ON p.mail_id=g.id WHERE p.return_of=?',(outbound,)).fetchall()
   self.assertEqual(returned,[(1,25,1001,outbound)])
  ROWS.append(dict(stage='internal-expiry-return-to-pending-actor-compatible',return_ED=25,source_id=outbound,passed=True))
  # Controlled old-schema representation, not a production migration: keep
  # ownership and mail tables, omit the optional modern lifecycle table.
  with closing(sqlite3.connect(self.path)) as db,db:db.execute('DROP TABLE character_lifecycle')
  self.send('legacy-without-lifecycle')
  with closing(sqlite3.connect(self.path)) as db:
   self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='character_lifecycle'").fetchone())
   with self.assertRaisesRegex(game_mail.MailError,'requires transaction'):game_mail._active_owner(db,1,1001)
   db.execute('BEGIN IMMEDIATE')
   with self.assertRaisesRegex(game_mail.MailError,'ownership mismatch'):game_mail._active_owner(db,2,1001)
   with self.assertRaisesRegex(game_mail.MailError,'ownership mismatch'):game_mail._active_owner(db,1,self.target)
   game_mail._active_owner(db,1,1001);db.rollback()
  ROWS.append(dict(stage='legacy-missing-lifecycle-query-only-and-ownership',legacy_send_passed=True,no_lifecycle_table_created=True,transaction_required=True,foreign_owner_rejected=True))


if __name__=='__main__':unittest.main()
