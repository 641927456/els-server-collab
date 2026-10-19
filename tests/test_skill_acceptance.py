"""Native proof must include parsed slots, matching notification and no crash."""
import json,sys,tempfile,shutil
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from verify_skills import verify
source=BASE/'analysis/runs/20261012-205818-321411'
assert verify(source)['initial_skills_verified'] and verify(source)['native_equip_ack_verified']
with tempfile.TemporaryDirectory(prefix='skills-acceptance-',dir=BASE/'analysis') as folder:
 target=Path(folder);shutil.copyfile(source/'local-bootstrap.json',target/'local-bootstrap.json')
 original=[json.loads(l) for l in (source/'launch-loopback-trace.jsonl').read_text(encoding='utf8').splitlines()]
 def check(rows):
  (target/'launch-loopback-trace.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf8')
  return verify(target)
 assert not check([r for r in original if r.get('payload',{}).get('event')!='native_skill_slots'])['initial_skills_verified']
 assert not check(original+[{'type':'error','description':'negative control'}])['initial_skills_verified']
 assert not check([r for r in original if not (r.get('payload',{}).get('event')=='request_wait_removed' and r.get('payload',{}).get('message')==0x123)])['native_equip_ack_verified']
 rows=json.loads(json.dumps(original))
 for r in rows:
  if r.get('payload',{}).get('event')=='native_skill_slots':r['payload']['records'][0]['level']=0
 assert not check(rows)['initial_skills_verified']
print('PASS: original skill initialization/equip proof; missing snapshots/waits, wrong native levels and probe errors rejected.')
