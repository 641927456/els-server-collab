from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json, sqlite3, struct, tempfile, unittest
from els_server.storage import game_mail, mailbox_extras
from els_server.domain import mailbox_extras as flow


class MailScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            game_mail.ensure(db)
            db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY,name TEXT NOT NULL)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
            db.executemany('INSERT INTO characters VALUES (?,?)', [(1001,'RoleA'),(1002,'RoleB'),(1003,'Other')])
            db.executemany('INSERT INTO character_owners VALUES (?,?)', [(1001,2),(1002,2),(1003,3)])

    def letter(self, mid, *, account=2, recipient=None, scope=False, read=False, deleted=False, expires=1000):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('''INSERT INTO game_mail(id,campaign,account_id,sender,title,body,ed,created_at,expires_at,read_at,deleted_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (mid,'fixture-'+str(mid),account,'Synthetic','Title','Body',0,100,expires,150 if read else None,150 if deleted else None))
            if recipient is not None:
                if scope:
                    db.execute('''CREATE TABLE IF NOT EXISTS online2026_mail_scope(
                        mail_id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL,recipient_uid INTEGER NOT NULL,deadline INTEGER NOT NULL)''')
                    db.execute('INSERT INTO online2026_mail_scope VALUES(?,?,?,?)',(mid,account,recipient,expires))
                else:
                    db.execute('INSERT INTO player_mail_meta VALUES(?,?,?,?,NULL,NULL)',(mid,recipient,3,1003))

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:
            return tuple(db.iterdump())

    def status(self, uid, account=2):
        return mailbox_extras.status(self.path,account,uid,now=200)

    def test_original_cross_character_scope_reproduction(self):
        self.letter(1,recipient=1002,scope=True)
        before=self.snapshot()
        self.assertEqual(game_mail.inbox(self.path,2,1001,now=200)[0],0)
        self.assertEqual(self.status(1001),(0,0,0))
        self.assertEqual(self.status(1002),(1,1,1))
        self.assertEqual(self.snapshot(),before)

    def test_mixed_account_player_and_scoped_letters_match_inbox(self):
        self.letter(1,recipient=1002,scope=True)
        self.letter(2)
        self.letter(3,recipient=1001)
        self.letter(4,account=3,recipient=1003)
        self.letter(5,recipient=1001,scope=True,read=True)
        self.letter(6,recipient=1001,scope=True,deleted=True)
        self.letter(7,recipient=1001,scope=True,expires=200)
        before=self.snapshot()
        for uid,account,want in [(1001,2,(3,2,5)),(1002,2,(2,2,2)),(1003,3,(1,1,4))]:
            with self.subTest(uid=uid):
                self.assertEqual(self.status(uid,account),want)
                count,rows=game_mail.inbox(self.path,account,uid,now=200)
                self.assertEqual(count,want[0])
                self.assertEqual(max((row['id'] for row in rows),default=0),want[2])
        self.assertEqual(self.snapshot(),before)

    def test_legacy_database_without_scope_table(self):
        self.letter(1,recipient=1002)
        self.letter(2,read=True)
        self.letter(3,recipient=1001,deleted=True)
        self.letter(4,expires=200)
        before=self.snapshot()
        self.assertEqual(self.status(1001),(1,0,2))
        self.assertEqual(self.status(1002),(2,1,2))
        self.assertEqual(self.snapshot(),before)

    def test_read_transition_and_encoder_failure_rollback(self):
        self.letter(1,recipient=1001,scope=True)
        before=self.snapshot()
        def reject(_): raise RuntimeError('controlled encoder failure')
        with self.assertRaises(RuntimeError):game_mail.read(self.path,2,1001,1,reject,now=200)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.status(1001),(1,1,1))
        game_mail.read(self.path,2,1001,1,lambda row: row['id'],now=200)
        self.assertEqual(self.status(1001),(1,0,1))
        self.assertEqual(self.status(1002),(0,0,0))

    def test_owner_guard_remains_and_does_not_write(self):
        self.letter(1,account=3,recipient=1003,scope=True)
        before=self.snapshot()
        with self.assertRaises(game_mail.MailError):self.status(1003,2)
        self.assertEqual(self.snapshot(),before)

    def test_existing_notification_clears_invisible_unread(self):
        self.letter(1,recipient=1002,scope=True)
        session=SimpleNamespace(client_build='dx11_260923',role='game',phase='town_ready',item_test=True,
            account=SimpleNamespace(account_id=2,uid=1001,store=SimpleNamespace(path=self.path)))
        from els_server.storage import player_mail
        before=self.snapshot()
        original=mailbox_extras.status
        with patch.object(player_mail,'maintenance',return_value=0),patch.object(flow.time,'monotonic',return_value=100),patch.object(mailbox_extras,'status',side_effect=lambda path,account,uid:original(path,account,uid,now=200)):
            output=flow.periodic(session,force=True)
        self.assertEqual(len(output),1)
        self.assertEqual(output[0].kind,0x1ce)
        self.assertEqual(struct.unpack('>IBiIB',output[0].payload),(1,0,0,0,0))
        self.assertEqual(self.snapshot(),before)


if __name__=='__main__': unittest.main()
