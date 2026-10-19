"""Saved native login needs independent scalar, receipt, process and UI evidence."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_reward_relogin import evaluate
run=ROOT/'analysis/client-6c6b5180/20261013-210921';source=json.loads((run/'saved-reward-login-snapshot.json').read_text(encoding='utf8'))
assert evaluate(source,run)['isolated_saved_reward_native_relogin_verified']
def reject(f):
 s=copy.deepcopy(source);f(s);assert not evaluate(s,run)['isolated_saved_reward_native_relogin_verified']
reject(lambda s:s['database']['balances'][0].__setitem__(1,240))
reject(lambda s:s['database']['receipts'].clear())
reject(lambda s:s.update(prior_grant_snapshot_sha256='bad'))
reject(lambda s:s['identity'].update(reward_probe=True))
reject(lambda s:s['identity'].update(created=0))
reject(lambda s:s['visual_review'].update(experience_percent=0))
reject(lambda s:s['visual_review'].update(sha256='bad'))
reject(lambda s:s.update(rows=[r for r in s['rows'] if r.get('payload',{}).get('event')!='character_full_dto_parsed']))
reject(lambda s:s.update(rows=[r for r in s['rows'] if r.get('payload',{}).get('event')!='readonly_owned_economy']))
reject(lambda s:s['server'].append({'event':'local_dungeon_reward_committed'}))
reject(lambda s:s['rows'].append({'type':'extension_error'}))
print('PASS: original restart restores saved scalars/EXP bar, unchanged receipt; missing, conflicting or duplicated evidence rejected.')
