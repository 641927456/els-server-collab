"""Validate the exact additive scene-source declarations without private resources."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parent
def sha(raw):return hashlib.sha256(raw).hexdigest()
def ast_sha(node):return sha(ast.dump(node,include_attributes=False).encode())
def main():
 c=json.loads((ROOT/'source-contract.json').read_bytes());assert len(c['files'])==1
 r=c['files'][0];raw=(ROOT/'source'/r['path']).read_bytes()
 assert r['path']=='els_server/domain/scene_retirement_sources.py'
 assert len(raw)==r['size'] and sha(raw)==r['sha256']
 tree=ast.parse(raw.decode());baseline=ast.Module(body=tree.body[:-1],type_ignores=[])
 assert ast_sha(baseline)==c['retirement_baseline_module_ast_sha256']
 extra=tree.body[-1]
 assert isinstance(extra,ast.AugAssign) and isinstance(extra.op,ast.Add) and extra.target.id=='RULES'
 assert ast_sha(extra)==c['appended_rules_ast_sha256']
 rules=ast.literal_eval(extra.value);assert len(rules)==c['appended_sources']==27
 assert {str(d):sum(r['dungeon']==d for r in rules) for d in {r['dungeon'] for r in rules}}==c['appended_by_dungeon']
 assert {(r['dungeon'],r['source']['template']) for r in rules}=={(34760,8288),(34720,8188)}
 for p in (ROOT/'tests').glob('*.py'):ast.parse(p.read_text())
 print(json.dumps({'ok':True,'source_files':1,'existing_declarations_preserved':True,'added_sources':27,'server_protocol_executed':False,'native_game_executed':False}))
if __name__=='__main__':main()
