from contextlib import closing
import asyncio,json,sqlite3,tempfile,unittest
import test_common as f
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.storage.characters import Characters

class Friends(f.Common):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='owned-box-friends-');self.addCleanup(self.tmp.cleanup);folder=f.Path(self.tmp.name);self.path=folder/'game.sqlite3'
  self.app=Application(ServerConfig(mode='friends',state_file=self.path,accounts_file=folder/'accounts.sqlite3',tls_cert=folder/'certificate.pem',tls_key=folder/'key.pem'))
  self.addCleanup(self.app.close)
  asyncio.run(self.app.start());self.addCleanup(self.app.registry.close)
  registration=self.app.registry.create('isolated_boxes');identity=self.app.registry.authenticate(registration['name'],registration['token'])
  roster=Characters(self.path,identity['id']);self.uid=roster.create('OwnBoxes',1,'isolated-friends-owner')['uid'];self.other=roster.create('OwnOther',5,'isolated-friends-other')['uid']
  self.s=asyncio.run(self.app.session(identity=identity));self.root=self.s.account.root;self.account=self.root.for_character(self.uid)
  self.s.account=self.account;self.s.role='game';self.s.phase='town_ready';self.s.enter_town=True;self.s.completed.update((0x28,0x225,0x227));self.app.playing[identity['id']]=self.s
  self.s.active_map=self.s.pending_map=self.account.get_location()['map'];self.account.get_inventory_snapshot();self.root.for_character(self.other).get_inventory_snapshot();self.career(150)
 def test_cartridge_current_friends_actor(self):self.exercise(119335,'cartridge_selection_box',True)
 def test_parent_current_friends_actor(self):self.exercise(723612,'published_2026_bundles',True)
 def test_titles_current_friends_actor(self):self.exercise(723673,'boosting_2026_title_rewards',True)
 def test_gear_current_friends_actor(self):self.exercise(723680,'boosting_2026_participation_gear',True)

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Friends(n)for n in Friends.__dict__ if n.startswith('test_')))
 out=dict(ok=result.wasSuccessful(),tests=result.testsRun,errors=[s for _,s in result.errors],failures=[s for _,s in result.failures],rows=f.ROWS,actual_Application_FriendsSession=True,private_synthetic_databases=True)
 (f.H/'tests-friends.json').write_text(json.dumps(out,indent=2),encoding='utf8');raise SystemExit(not result.wasSuccessful())
