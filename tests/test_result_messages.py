import json,tempfile,unittest
from pathlib import Path
from els_server.result_messages import ResultMessages,result_messages
from els_server.game_data import DATA_DIR


class ResultMessageTests(unittest.TestCase):
    def test_pinned_build_and_known_native_messages(self):
        catalog=result_messages();self.assertEqual(catalog.manifest['count'],3150)
        self.assertEqual(catalog.text(0),'成功')
        self.assertEqual(catalog.text(464),'艾尔结晶不足，无法赋予属性。')
        self.assertEqual(catalog.text(658),'手续费不足，无法删除属性。')
        self.assertEqual(catalog.text(459),'背包内没有此道具。')
        for n in (True,1.0,None,2**31):
            with self.assertRaises(ValueError):catalog.text(n)
        self.assertEqual(catalog.text(-1),catalog.text(3150))

    def test_corrupt_or_incomplete_catalog_rejected(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=(DATA_DIR/'result_messages.json').read_bytes();manifest=(DATA_DIR/'result_messages.manifest.json').read_bytes()
            (root/'result_messages.json').write_bytes(raw+b' ');(root/'result_messages.manifest.json').write_bytes(manifest)
            with self.assertRaises(ValueError):ResultMessages(root)
            data=json.loads(raw);data['messages'].pop();raw=json.dumps(data).encode();m=json.loads(manifest);m['sha256']=hashlib.sha256(raw).hexdigest()
            (root/'result_messages.json').write_bytes(raw);(root/'result_messages.manifest.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):ResultMessages(root)
