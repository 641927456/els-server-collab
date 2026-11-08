from pathlib import Path
import ast,hashlib,json,subprocess
R=Path('G:/els');H=Path(__file__).resolve().parent;C=H/'integrated-source';read=lambda p:json.loads(p.read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest();parents=read(H/'parents.json');BASE=R/parents['online']['path'];bulk=R/'analysis/stackable-box-final-20261108-v1/local-policy-v1/source';old=R/'releases/online/native-housing-expansion-presets-20261108-v1';report=read(H/'merge-report.json');resolved=[]
p='els_server/domain/consumable_flow.py';text=(BASE/p).read_text('utf8');assert text.count('except ConsumableCoolingDown:return [acknowledgement(result=1369,automatic=automatic)]')==1;text=text.replace('except ConsumableCoolingDown:return [acknowledgement(result=1369,automatic=automatic)]','except ConsumableCoolingDown as error:return [acknowledgement(result=1369,automatic=automatic,slot=error.slot)]');(C/p).write_text(text,'utf8');resolved.append(dict(path=p,resolution='Keep current independent lane authorize callback and echo exact pet slot on cooldown refusal'))
p='els_server/domain/acquisition_policy.py';text=(BASE/p).read_text('utf8');new=(bulk/p).read_text('utf8');start=new.index('    from els_server.domain.retained_box_openings');end=new.index('    from els_server.domain.pet_trainer_exchange',start);anchor='    from els_server.domain.pet_trainer_exchange';assert text.count(anchor)==1;text=text.replace(anchor,new[start:end]+anchor,1);(C/p).write_text(text,'utf8');resolved.append(dict(path=p,resolution='Keep current approved ticket source first; append exact owned-box source authorization'))
p='els_server/domain/inventory_items.py';paths=[H/'merge-inputs'/('inventory-normalized-'+s)for s in('current','base','candidate')]
for path,source in zip(paths,(BASE/p,old/p,bulk/p)):path.write_bytes(source.read_bytes().replace(b'\r\n',b'\n'))
q=subprocess.run(['git','merge-file','-p','--diff3',*[str(p)for p in paths]],capture_output=True);assert q.returncode==0,q.stdout[-1500:];(C/p).write_bytes(q.stdout);resolved.append(dict(path=p,resolution='Normalize CRLF for comparison only; preserve current reset ticket and all finite owned-box/fishing readers'))
p='tools/client_compatibility_profiles.json';data=read(BASE/p);before=read(old/p);candidate=read(bulk/p);byid={r['id']:r for r in before['profiles']}
for changed in candidate['profiles']:
 current=next(r for r in data['profiles']if r['id']==changed['id']);original=byid[changed['id']]
 for field,value in changed.items():
  if field=='artifacts':
   for name,pin in value.items():
    if pin!=original['artifacts'].get(name):current['artifacts'][name]=pin
  elif value!=original.get(field):
   assert current.get(field)in(original.get(field),value),(field,'conflicting profile field');current[field]=value
for profile in data['profiles']:
 if profile['id']!='cn-dx11-6c6b5180':continue
 for name in list(profile['artifacts']):
  if(C/name).exists():profile['artifacts'][name]=sha((C/name).read_bytes())
 for name in('tools/native_hit_count_obstacles.py','tools/native_hit_count_obstacles.js'):profile['artifacts'][name]=sha((C/name).read_bytes())
 assert len(profile['artifacts'])<=64
(C/p).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8');resolved.append(dict(path=p,resolution='Preserve current V113 profile, merge three owned-key dependencies and bind every merged source hash'))
for path in C.rglob('*.py'):ast.parse(path.read_bytes())
files=[]
for path in sorted(C.rglob('*')):
 if not path.is_file()or path.name.endswith('.conflict'):continue
 relative=path.relative_to(C).as_posix();raw=path.read_bytes();prior=(BASE/relative).read_bytes()if(BASE/relative).exists()else None
 files.append(dict(path=relative,parent_sha256=sha(prior)if prior is not None else None,sha256=sha(raw),size=len(raw)))
assert len(files)==46
report.update(ok=True,conflicts_resolved=resolved,conflicts=[],files=files);(H/'merge-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
(H/'candidate.json').write_text(json.dumps(dict(status='integrated_candidate_review_pending',source=str(C),parent=parents['online'],files=files,original_EXE_KOM_modified=False,player_data_modified=False,source_Git_submitted=False,independent_hook_review=False),ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(dict(ok=True,files=len(files),resolutions=resolved,profile_dependencies=len(data['profiles'][0]['artifacts']))))
