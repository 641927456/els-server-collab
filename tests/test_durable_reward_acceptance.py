"""Frozen real grant is rejected when protocol, ledger or pixel proof is lost."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_durable_rewards import evaluate
run=ROOT/'analysis/client-6c6b5180/20261013-204334'
source=json.loads((run/'durable-reward-phase-snapshot.json').read_text(encoding='utf8'))
assert evaluate(source,run)['isolated_ed_experience_grant_verified']
def reject(change):
 s=copy.deepcopy(source);change(s);assert not evaluate(s,run)['isolated_ed_experience_grant_verified']
reject(lambda s:s['identity'].update(reward_probe=True))
reject(lambda s:s['database']['balances'][0].__setitem__(1,240))
reject(lambda s:s['database']['receipts'][0].update(response_hex='00'))
reject(lambda s:s['database']['receipts'][0].update(proof_sha256='0'*64))
reject(lambda s:s['database']['receipts'][0].update(run_id='noncanonical'))
reject(lambda s:s['visual_review'].update(ed=0))
reject(lambda s:s['visual_review']['screenshots'].update({'clear-ui-2.png':'bad'}))
reject(lambda s:s.update(rows=[r for r in s['rows'] if r.get('payload',{}).get('event')!='native_lifecycle_packet']))
reject(lambda s:s.update(rows=[r for r in s['rows'] if r.get('payload',{}).get('event')!='native_network_npc_death']))
reject(lambda s:s.update(server=[r for r in s['server'] if r.get('event')!='local_dungeon_reward_committed']))
reject(lambda s:s['server'].append({'event':'local_business_response_sent','kind':0xc1}))
reject(lambda s:s['server'].append({'event':'protocol_error'}))
reject(lambda s:s['rows'].append({'type':'send','payload':{'event':'experimental_clear'}}))
print('PASS: real Boss grant and saved receipt agree; missing evidence, tampering, duplicates and private clear rejected.')

second=ROOT/'analysis/client-6c6b5180/20261013-211757'
source=json.loads((second/'durable-reward-phase-snapshot.json').read_text(encoding='utf8'));run=second
assert evaluate(source,run)['isolated_ed_experience_grant_verified']
reject(lambda s:s.update(prior_grant_snapshot_sha256='bad'))
reject(lambda s:s['database']['receipts'][0].update(proof_sha256='bad'))
reject(lambda s:s['database']['balances'][0].__setitem__(2,50))
reject(lambda s:s.update(rows=[r for r in s['rows'] if r.get('payload',{}).get('event')!='native_owned_economy_sync_consumed']))
reject(lambda s:s.update(rows=[r for r in s['rows'] if not (r.get('payload',{}).get('event')=='readonly_owned_economy' and r['payload'].get('scalar108')==100)]))
reject(lambda s:s['visual_review'].update(experience_percent=8.3))
print('PASS: second grant preserves first receipt, accumulates once and restores native totals after clear; broken baseline or sync rejected.')
