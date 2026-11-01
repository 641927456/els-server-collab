"""Verify frozen provenance and recorded scope; does not run Application/TLS or activate source."""
from pathlib import Path
import hashlib,json
O=Path(__file__).resolve().parent;ROOT=O.parents[1]
H=lambda b:hashlib.sha256(b).hexdigest()
J=lambda p:json.loads(p.read_bytes())
c=J(O/'source-contract.json');assert c['candidate']and not c['activation']and not c['runtime_acceptance']
assert len(c['files'])==1 and c['files'][0]['path']=='els_server/data/native_line_triggers.json'
def checked(name,sha):
 p=ROOT/name;assert p.resolve().is_relative_to((ROOT/'references').resolve());b=p.read_bytes();assert H(b)==sha;return json.loads(b)
target=checked(c['files'][0]['source'],c['files'][0]['sha256'])['rules']
parent=checked(c['parent_rules']['source'],c['parent_rules']['sha256'])['rules']
for e in c['evidence']:checked(e['path'],e['sha256'])
key=lambda r:(r['dungeon'],r['stage'],r['part'],r.get('trigger',r.get('activation')))
addition=J(O/'rule-additions.json');qualified=J(O/'qualified-additions.json')
assert len(parent)==28 and len(addition)==80 and len(target)==108 and len(qualified)==69
assert target==parent+addition and len({key(r)for r in target})==108
assert all(type(r['native_loop'])is bool and all(len(r[k])==64 and set(r[k])<=set('0123456789abcdef')for k in ['source_sha256','line_source_sha256','world_source_sha256'])for r in addition)
assert all(r['native_predicates_and_AI_retained']is True for r in addition)
new=[x['rule']for x in qualified];assert all(r in addition for r in new)and len({key(r)for r in new})==69
prior=[r for r in addition if key(r)not in {key(x)for x in new}];assert len(prior)==11
assert sum(r['native_loop']for r in new)==2 and all(r['dungeon']==35320 for r in new if r['native_loop'])
for x in qualified:assert x['native_action'] and x['native_action']['TRIGGER_ID']==x['rule']['trigger']and x['native_action']['TRIGGER_LOOP']==x['rule']['native_loop']
for mode in ['online','local']:
 t=J(O/('server-TLS-'+mode+'.json'));assert t['ok']and t['actual_Application_TLS']and t['controlled_owned_room_matrix']and not t['natural_clear']
 assert len(t['cases'])==69 and {key(r)for r in t['cases']}=={key(r)for r in new} and len(t['negative_cases'])==17
 assert t['native_loop_notifications_for_two_35320_contexts']and t['non_loop_duplicate_ACK_only']and t['no_HP_defeat_room_or_inventory_change']
 p=J(O/('reused/labyrinth-TLS-'+mode+'.json'));assert p['ok']and p['actual_Application_TLS']and len(p['cases'])==11 and {key(r)for r in p['cases']}=={key(r)for r in prior}
assert J(O/'config-result.json')['ok']
assert J(O/'reused/application-qualification.json')['ok']
assert J(O/'reused/native-contact-result.json')['ok']and J(O/'reused/native-false-contact-result.json')['ok']
print(json.dumps(dict(ok=True,files=1,preserved=28,added=80,total=108,recorded_new_TLS_cases_each=69,recorded_prior_TLS_cases_each=11,recorded_rejections_each=17,Application_or_Game_reexecuted=False)))
