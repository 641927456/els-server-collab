"""Portable integrity of the exact installed field-entry source archive."""
from pathlib import Path
import ast,hashlib,json
R=Path(__file__).resolve().parents[1]
D=R/'references/native-field-entry-20261101-v1'
def main():
 c=json.loads((D/'source-contract.json').read_bytes())
 assert c['source_archive_only'] and not c['root_engine_activated']
 expected={'els_server/domain/field_travel.py','els_server/protocol/field_boss_messages.py'}
 pinned={}
 for channel in ('online','local'):
  rows=c['channels'][channel]['changes'];assert {r['path']for r in rows}==expected
  for row in rows:
   source=R/row['source'];assert source.resolve().is_relative_to((D/'source/common').resolve())
   raw=source.read_bytes();assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256']
   ast.parse(raw);assert row['parent_sha256']!=row['sha256']
   if row['path']in pinned:assert pinned[row['path']]==row['sha256']
   pinned[row['path']]=row['sha256']
 assert c['validation']['native_packet_fields']==25 and c['validation']['authenticated_reachable_edges']==76
 print(json.dumps(dict(ok=True,channels=2,unique_sources=len(pinned),source_archive_only=True,private_native_tests_repeated=False)))
if __name__=='__main__':main()
