import json, sqlite3, tempfile, unittest, uuid
from contextlib import closing
from pathlib import Path
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage import gm_mail_queue


class GmMailDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()

    def job(self, template, option_groups=None):
        return dict(operation_id=str(uuid.uuid4()), uid=1001, template=template, quantity=1,
                    option_groups=option_groups, title='GM 邮件', body='测试发放', reason='测试', sender='GM')

    def attachments(self):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute('SELECT item_json FROM player_mail_items').fetchall()
        return [json.loads(raw)['template'] for (raw,) in rows]

    def test_mail_delivers_unverified_accessory(self):
        gm_mail_queue.enqueue(self.path, self.job(42303))
        self.assertEqual(gm_mail_queue.process(self.path), 1)
        self.assertIn(42303, self.attachments())
        self.assertEqual(gm_mail_queue.status(self.path)['failed'], [])

    def test_mail_delivers_t_circuit_with_options(self):
        from els_server.domain.gm_item_options import spec
        option = spec(118590)['choices'][0]['id']
        gm_mail_queue.enqueue(self.path, self.job(118590, {'1': [option]}))
        self.assertEqual(gm_mail_queue.process(self.path), 1)
        self.assertIn(118590, self.attachments())
        self.assertEqual(gm_mail_queue.status(self.path)['failed'], [])


    def test_online_item_grant_falls_back_to_mail(self):
        from launcher.service import LauncherService
        service = LauncherService(save=self.path)
        receipt = service._item_mail_fallback(str(uuid.uuid4()), 1001,
                                              {'template': 42303, 'quantity': 1, 'option_groups': None})
        self.assertEqual(receipt['state'], 'queued')
        self.assertEqual(gm_mail_queue.process(self.path), 1)
        self.assertIn(42303, self.attachments())


if __name__ == '__main__':
    unittest.main()
