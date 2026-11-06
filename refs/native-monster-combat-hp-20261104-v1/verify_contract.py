from pathlib import Path
import ast,hashlib,json
W=Path(__file__).resolve().parent
J=lambda p:json.loads(Path(p).read_bytes())
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
c=J(W/'source-contract.json');scope=J(W/'scope.json')
assert len(c['files'])==5 and H(W/'scope.json')==c['scope_sha256']
for name,digest in c['files'].items():
 p=W/'source'/name;assert H(p)==digest,name
 if p.suffix=='.py':ast.parse(p.read_text('utf8'))
for name,digest in c['evidence'].items():assert H(W/name)==digest
for name in ('formal_npc_hp','boss_npc_stats'):
 assert H(W/f'source/els_server/data/{name}.json')==J(W/f'source/els_server/data/{name}.manifest.json')['payload_sha256']
hp=J(W/'source/els_server/data/formal_npc_hp.json');stats=J(W/'source/els_server/data/boss_npc_stats.json')
assert len(scope['small_changes'])==66 and len({r['template']for r in scope['small_changes']})==54
for r in scope['small_changes']:
 item=hp['maps'][str(r['map'])]['combat_hp_overrides'][str(r['template'])]
 assert item['hp_float32']==r['after']and item['expected_script_hp']==r['before']and item['level']==r['level']
for r in scope['master_hp']:assert hp['maps'][str(r['map'])]['public_hp_templates'][str(r['template'])]['hp_float32']==r['hp']
for r in scope['master_child_stats']:
 item=stats['maps'][str(r['map'])]['dynamic']['0:'+str(r['template'])]
 assert item['raw_attack_defense']==r['raw_attack_defense']and item['six_resistances']==r['six_resistances']
q=J(W/'evidence/small-hp-validation.json');web=J(W/'evidence/website-function-replay.json')
assert q['passed']and q['repaired_combat_templates']==54 and q['total_contexts']==18865 and q['actual_spawn_template_pairs']==66
assert web['passed']and web['cases']==66 and q['candidate_manifest_sha256']==web['candidate_manifest_sha256']==c['original_qualification_manifest_sha256']
assert J(W/'evidence/master-validation.json')['passed']and J(W/'evidence/master-review.json')['candidate_review_passed']
assert J(W/'evidence/rebased-validation.json')['passed']and J(W/'evidence/rebased-validation.json')['candidate_manifest_sha256']==c['candidate_manifest_sha256']
print('5 exact runtime files;54 combat templates/66 pairs;17 Master HP;24 child stats;18865 sources;website replay66')
