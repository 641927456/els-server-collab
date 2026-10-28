import hashlib,json,tempfile,unittest
from pathlib import Path
from tools import verify_current_refresh_archive_20261027 as verify
from tools.materialize_formal_runtime import load_manifest,plan

class DeliveredIdentityRefresh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile=load_manifest(verify.ROOT/'channels/current-engine.json',verify.ROOT)
        cls.selected={mode:{r['path']:(r,p)for r,p in plan(verify.ROOT,cls.profile,mode)}
                      for mode in ('online','local')}

    def test_complete_delivered_projection_reverses_to_accepted_parent(self):
        for mode in ('online','local'):
            entry,path=self.selected[mode]['els_server/storage/career_shop.py']
            prior,parent=verify.verified_identity_predecessor(mode,entry,path)
            self.assertNotEqual(entry['sha256'],prior['sha256'])
            self.assertEqual(hashlib.sha256(parent.read_bytes()).hexdigest(),prior['sha256'])

    def test_changed_selected_bytes_do_not_inherit_refresh_qualification(self):
        entry,path=self.selected['online']['els_server/storage/career_shop.py']
        with tempfile.TemporaryDirectory()as folder:
            changed=Path(folder)/'career_shop.py'
            changed.write_bytes(path.read_bytes()+b'\n# unapproved source replacement\n')
            with self.assertRaises(AssertionError):
                verify.verified_identity_predecessor('online',entry,changed)

    def test_equal_bytes_at_unaccepted_source_location_are_rejected(self):
        entry,path=self.selected['local']['els_server/storage/career_shop.py']
        forged={**entry,'source':'references/unaccepted/career_shop.py'}
        with self.assertRaises(AssertionError):
            verify.verified_identity_predecessor('local',forged,path)

    def test_unknown_rewrite_still_fails_original_master_successor_gate(self):
        entry,path=self.selected['online']['els_server/storage/career_shop.py']
        unknown={**entry,'sha256':'0'*64}
        actual,unchanged=verify.verified_identity_predecessor('online',unknown,path)
        self.assertEqual(actual,unknown)
        archive=json.loads((verify.ROOT/'references/current-refresh-combat-inputs-20261027-v1/manifest.json').read_bytes())
        row=next(r for r in archive['files']if r['path']==entry['path'])
        expected=verify.function((verify.ROOT/row['source']).read_text('utf8'),'notifications')
        with self.assertRaises(AssertionError):
            verify.verified_Master_successor(self.profile,'online',row,actual,unchanged,expected)

if __name__=='__main__':unittest.main()
