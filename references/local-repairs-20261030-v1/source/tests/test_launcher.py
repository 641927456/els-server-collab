"""GM transactions, isolation, real save leases, backup and HTTP boundaries."""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launcher.service import LauncherService
from launcher.__main__ import LauncherHTTP
from els_server.storage.lifecycle import SaveLease
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import load_items
from els_server.game_data import client_data


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root/'save.sqlite3'
        account = LocalAccount(LocalState(self.path))
        account.enable_characters()
        account.enable_rewards(); account.enable_inventory()
        account.characters.create('测试伊芙', 5, str(uuid.uuid4()))
        self.service = LauncherService(self.root, self.path)
        self.offline = patch('launcher.service.games', return_value=[])
        self.offline.start()

    def tearDown(self):
        self.offline.stop(); self.temp.cleanup()

    def request(self, action='ed', value=1000, uid=1001):
        character = next(c for c in self.service.characters() if c['uid'] == uid)
        return dict(operation_id=str(uuid.uuid4()), uid=uid, version=character['version'], action=action, value=value)

    def scalar(self, sql, parameters=()):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute(sql, parameters).fetchone()[0]

    def test_ed_isolated_idempotent_and_backup_precedes_mutation(self):
        request = self.request()
        before = self.scalar('SELECT ed FROM reward_balances WHERE uid=1001')
        result = self.service.mutate(request)
        self.assertEqual(result, self.service.mutate(request))
        self.assertEqual(self.scalar('SELECT ed FROM reward_balances WHERE uid=1001'), before+1000)
        self.assertEqual(self.scalar('SELECT ed FROM reward_balances WHERE uid=1002'), 0)
        with closing(sqlite3.connect(self.service.backups/result['backup'])) as backup:
            self.assertEqual(backup.execute('SELECT ed FROM reward_balances WHERE uid=1001').fetchone()[0], before)
            self.assertEqual(backup.execute('PRAGMA quick_check').fetchone(), ('ok',))
        self.assertEqual(len(self.service.history()), 1)

    def test_stale_form_online_and_server_lease_refused(self):
        request = self.request()
        self.service.mutate(self.request('ed', 50))
        with self.assertRaisesRegex(ValueError, '已变化'):
            self.service.mutate(request)
        with patch('launcher.service.games', return_value=[123]):
            with self.assertRaisesRegex(ValueError, '退出游戏'):
                self.service.mutate(self.request())
        with SaveLease(self.path):
            self.assertTrue(self.service.state()['gm_locked'])
            with self.assertRaisesRegex(ValueError, '占用'):
                self.service.mutate(self.request())
        self.assertFalse(self.service.state()['gm_locked'])

    def test_level_and_experience_consistent_no_downgrade(self):
        self.service.mutate(self.request('level', 70, 1002))
        self.assertEqual(self.scalar('SELECT level FROM characters WHERE uid=1002'), 70)
        self.assertEqual(self.scalar('SELECT experience FROM reward_balances WHERE uid=1002'), client_data().thresholds[69])
        self.assertEqual(self.scalar('SELECT level FROM characters WHERE uid=1001'), 1)
        with self.assertRaises(ValueError):self.service.mutate(self.request('level', 15, 1002))
        with self.assertRaises(ValueError):self.service.mutate(self.request('level', 100, 1002))

    def test_item_grant_lands_in_mailbox_and_claims_into_bag(self):
        request = self.request('item', dict(template=77000, quantity=99), 1002)
        receipt = self.service.mutate(request)
        self.assertIn('邮箱', receipt['detail'])
        self.assertEqual(self.service.mutate(request), receipt)
        self.assertEqual([i for i in self.service.inventory(1002) if i['template'] == 77000], [])
        with closing(sqlite3.connect(self.path)) as db:
            mails = db.execute('SELECT id,account_id,ed FROM game_mail').fetchall()
            escrow = [json.loads(r[0]) for r in db.execute('SELECT item_json FROM player_mail_items')]
            recipients = db.execute('SELECT recipient_uid FROM player_mail_meta').fetchall()
        self.assertEqual([(m[1], m[2]) for m in mails], [(1, 0)])
        self.assertEqual(recipients, [(1002,)])
        self.assertEqual([(e['template'], e['count']) for e in escrow], [(77000, 99)])
        from els_server.storage import game_mail
        with self.assertRaises(game_mail.MailError):
            game_mail.claim(self.path, 1, 1001, [mails[0][0]], lambda ids, ed: (ids, ed))
        game_mail.claim(self.path, 1, 1002, [mails[0][0]], lambda ids, ed, changes: (ids, ed), include_items=True)
        self.assertEqual([(i['template'], i['count']) for i in self.service.inventory(1002)
                          if i['template'] == 77000], [(77000, 99)])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM game_mail'), 1)

    def test_item_mail_quantity_bounded_by_stack_and_nothing_written_on_error(self):
        from launcher.service import item_catalog
        single = next(r for r in item_catalog() if r['stack'] == 1)
        before = self.scalar('SELECT next_uid FROM inventory_sequence')
        with self.assertRaisesRegex(ValueError, '单封邮件'):
            self.service.mutate(self.request('item', dict(template=single['id'], quantity=2), 1002))
        self.assertEqual(self.scalar('SELECT next_uid FROM inventory_sequence'), before)
        self.assertEqual(self.scalar('''SELECT COUNT(*) FROM sqlite_master
                                        WHERE type='table' AND name='game_mail' '''), 0)

    def test_terminated_client_entry_does_not_count_as_running(self):
        import subprocess
        import types
        from launcher import service as launcher_service
        child = subprocess.Popen([sys.executable, '-c', 'pass'])
        child.wait()
        self.assertTrue(launcher_service.exited(child.pid))
        self.assertFalse(launcher_service.exited(os.getpid()))
        stale = types.SimpleNamespace(pid=child.pid, info={'name': 'x2_dx11.exe'})
        self.offline.stop()
        try:
            with patch('launcher.service.psutil.process_iter', return_value=[stale]):
                self.assertEqual(launcher_service.games(), [])
        finally:
            self.offline.start()

    def test_launch_scripts_ignore_terminated_client_entry(self):
        import subprocess
        import types
        sys.path.insert(0, str(ROOT/'tools'))
        from launch_friends_client import running_clients
        child = subprocess.Popen([sys.executable, '-c', 'pass'])
        child.wait()
        stale = types.SimpleNamespace(pid=child.pid, info={'name': 'x2_dx11.exe'})
        fake = types.SimpleNamespace(Error=Exception, process_iter=lambda columns: [stale])
        self.assertEqual(running_clients(fake), [])

    def test_town_other_role_preserved_and_input_bounds(self):
        LocalState(self.path,1002).save(20001,3,50,(3.,4.,5.))
        self.service.mutate(self.request('town',20000,1002))
        self.assertEqual(LocalState(self.path,1002).load()['map'],20000)
        for value in [0,-1,True,2_000_000_001,1.5,'50']:
            with self.assertRaises(ValueError):self.service.mutate(self.request('ed',value))
        with self.assertRaises(ValueError):self.service.mutate(self.request('item',dict(template=2147483646,quantity=1)))
        self.assertEqual(len(self.service.history()),1)

    def test_missing_save_read_does_not_create_db_and_isolated_launch_refused(self):
        service=LauncherService(self.root,self.root/'absent.sqlite3')
        self.assertEqual(service.characters(),[])
        self.assertFalse(service.save.exists())
        with self.assertRaises(ValueError):self.service.start()

    def test_search_and_backup_during_online_readonly(self):
        result=self.service.search_items('77000')
        self.assertTrue(any(r['id']==77000 for r in result['rows']))
        with patch('launcher.service.games',return_value=[123]),SaveLease(self.path):
            backup=self.service.backup()
        self.assertTrue(Path(backup['path']).is_file())
        self.assertEqual(self.service.history(),[])

    def test_http_token_origin_traversal_and_actual_gm(self):
        server=LauncherHTTP(self.service)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(route,body=None,token=None,origin=None):
            headers={}
            if token:headers['X-Launcher-Token']=token
            if origin:headers['Origin']=origin
            if body is not None:headers['Content-Type']='application/json'
            req=urllib.request.Request(server.origin+route,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            return urllib.request.urlopen(req)
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:request('/api/characters')
            self.assertEqual(error.exception.code,401)
            with self.assertRaises(urllib.error.HTTPError) as error:request('/api/gm',self.request(),server.token,'https://evil.invalid')
            self.assertEqual(error.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError) as error:request('/assets/../../state/integrated.sqlite3')
            self.assertEqual(error.exception.code,404)
            with request('/api/gm',self.request(),server.token,server.origin) as response:
                self.assertIn('backup',json.load(response)['data'])
            self.assertEqual(self.scalar('SELECT ed FROM reward_balances WHERE uid=1001'),1000)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    unittest.main()
