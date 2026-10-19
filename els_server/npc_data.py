"""Immutable native NPC identity catalog; no guessed combat/drop semantics."""
import hashlib,json
from pathlib import Path

class NpcData:
 def __init__(self,directory,client_sha,enum_sha):
  directory=Path(directory);self.manifest=json.loads((directory/'npcs.manifest.json').read_text(encoding='utf8'))
  raw=(directory/'npcs.json').read_bytes();m=self.manifest
  if m['schema_version']!=1 or m['client_sha256']!=client_sha or m['enum_sha256']!=enum_sha or hashlib.sha256(raw).hexdigest()!=m['payload_sha256']:
   raise ValueError('NPC data identity/checksum mismatch')
  rows=json.loads(raw)
  if len(rows)!=m['count'] or sum(len(r['variants']) for r in rows.values())!=m['registration_count']:raise ValueError('NPC catalog count')
  for key,row in rows.items():
   if str(row['id'])!=key or type(row['id']) is not int or row['id']<0 or type(row['class_id']) is not int or type(row['is_npc']) is not bool or not row['variants']:raise ValueError('NPC record shape')
   for variant in row['variants']:
    if (variant['NPC_ID'],variant['CLASS_TYPE'],variant['IS_NPC'],variant.get('LUA_FILE_NAME'))!=(row['id'],row['class_id'],row['is_npc'],row['script']):raise ValueError('Conflicting NPC variant')
  self._rows={int(k):json.dumps(v,ensure_ascii=False) for k,v in rows.items()}
 def npc(self,identity):
  if type(identity) is not int or identity not in self._rows:raise ValueError('Unknown native NPC identity')
  return json.loads(self._rows[identity])
