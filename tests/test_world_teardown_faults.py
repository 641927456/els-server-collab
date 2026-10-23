"""Private lifecycle faults; real SQLite transaction, no player DB or client."""
import argparse, json, sqlite3, sys, tempfile, unittest, uuid
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--runtime-root',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--temp-dir',type=Path)
options,remaining=parser.parse_known_args()
sys.argv=[sys.argv[0],*remaining]
BASE=options.runtime_root.resolve()
if options.temp_dir is not None:
    assert options.temp_dir.is_dir(),'--temp-dir must be an existing private directory'
sys.path.insert(0,str(BASE))
import els_server.domain
from els_server.application import FriendsSession
from els_server.domain.friends_world import FriendsWorld, Mailbox
from els_server.domain.friends_dungeon import Room
from els_server.storage import challenge_group


class WorldCleanup(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='owned-world-cleanup-',dir=options.temp_dir)
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'private.sqlite3'
        self.world=FriendsWorld()
        self.app=SimpleNamespace(world=self.world,playing={})
        self.leaving=self.session(2,1001)
        self.other=self.session(3,1002)
        self.unrelated=self.session(4,1003)
        self.app.playing[2]=self.leaving
        self.party={'id':900001,'members':[self.leaving,self.other],
                    'leader':self.leaving,'ready':{self.other},'run':None,'dungeon':30000}
        self.world.parties[900001]=self.party
        for member in self.party['members']:self.world.party_of[member]=self.party
        self.world.members={self.leaving:(1,20000),self.unrelated:(1,20000)}
        self.world.towns={(1,20000):{self.leaving:None,self.unrelated:None}}
        self.world.invitations={self.leaving:{'inviter':self.unrelated},
                                self.other:{'inviter':self.leaving},
                                self.unrelated:{'inviter':self.other}}

    def session(self,identity,uid):
        session=FriendsSession.__new__(FriendsSession)
        session.application=self.app;session.identity={'id':identity};session.released=False
        session.account=SimpleNamespace(uid=uid,store=SimpleNamespace(path=self.path))
        session.mailbox=Mailbox();session.social_overflow=False
        session.clear_notified=False;session.coop_error=None
        return session

    def assert_detached(self):
        self.assertTrue(self.leaving.released)
        self.assertNotIn(self.leaving,self.world.members)
        self.assertNotIn(self.leaving,self.world.towns[(1,20000)])
        self.assertIn(self.unrelated,self.world.members)
        self.assertNotIn(self.leaving,self.world.party_of)
        self.assertNotIn(self.other,self.world.party_of)
        self.assertNotIn(900001,self.world.parties)
        self.assertEqual(self.party['members'],[self.other])
        self.assertNotIn(self.leaving,self.world.invitations)
        self.assertNotIn(self.other,self.world.invitations)
        self.assertEqual(self.world.invitations,{self.unrelated:{'inviter':self.other}})

    def test_real_challenge_SQL_lock_does_not_strand_world_membership(self):
        attempt=str(uuid.uuid4())
        self.party['challenge']={'attempt':attempt}
        with closing(sqlite3.connect(self.path)) as db,db:
            challenge_group.schema(db)
            db.execute('INSERT INTO challenge_attempts VALUES(?,?,?,?,?,?,?)',(1001,attempt,4,0,1900000000,0,0))
            db.execute('INSERT INTO challenge_rosters VALUES(?,?,?)',(attempt,1001,json.dumps([1001,1002])))
        room=Room(self.party,(self.leaving,self.other),self.leaving,30000,str(uuid.uuid4()))
        self.party['run']=room
        self.world.dungeons.rooms={self.leaving:room,self.other:room}
        connect=sqlite3.connect
        with closing(connect(self.path)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            # Real abandon/BEGIN/rollback execute. Only lock wait is reduced.
            with patch.object(challenge_group.sqlite3,'connect',side_effect=lambda *a,**k:connect(*a,**dict(k,timeout=.05))):
                with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                    self.leaving.release()
            blocker.rollback()
        self.assert_detached()
        self.assertNotIn(2,self.app.playing)
        self.assertEqual(self.world.dungeons.rooms,{})
        self.assertIsNone(self.party['run'])
        self.assertEqual(self.other.coop_error,'Party dungeon aborted: member left')
        # Failed persistence remains failed; no fake abandon or retry.
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT uid,attempt FROM challenge_attempts').fetchall(),[(1001,attempt)])
            self.assertEqual(db.execute('SELECT attempt FROM challenge_rosters').fetchall(),[(attempt,)])

    def test_field_failure_attempts_town_party_invitations_and_preserves_new_lease(self):
        newer=object();self.app.playing[2]=newer
        with patch.object(self.world.field_bosses,'detach',side_effect=OSError('field teardown failed')):
            with self.assertRaisesRegex(OSError,'field teardown failed'):self.leaving.release()
        self.assert_detached()
        self.assertIs(self.app.playing[2],newer)

    def test_party_absent_does_not_suppress_earlier_exception(self):
        self.world.party_of.clear();self.world.parties.clear()
        with patch.object(self.world.field_bosses,'detach',side_effect=OSError('field teardown failed')):
            with self.assertRaisesRegex(OSError,'field teardown failed'):self.leaving.release()
        self.assertNotIn(2,self.app.playing)
        self.assertNotIn(self.leaving,self.world.members)
        self.assertNotIn(self.leaving,self.world.invitations)
        self.assertNotIn(self.other,self.world.invitations)

    def test_dungeon_failure_still_cleans_party_invitations_and_matching_lease(self):
        with patch.object(self.world.dungeons,'detach',side_effect=OSError('dungeon teardown failed')):
            with self.assertRaisesRegex(OSError,'dungeon teardown failed'):self.leaving.release()
        self.assert_detached()
        self.assertNotIn(2,self.app.playing)

    def test_normal_and_repeated_disconnect_preserves_unrelated_membership(self):
        self.leaving.release();self.assert_detached()
        self.leaving.release()
        self.assertEqual(self.world.invitations,{self.unrelated:{'inviter':self.other}})
        self.assertIn(self.unrelated,self.world.members)


if __name__=='__main__':unittest.main()
