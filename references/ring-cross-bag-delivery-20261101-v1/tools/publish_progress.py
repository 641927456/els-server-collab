from delivery_common import *
import ast,copy,os,re,subprocess,sys
P=W/'publication';h=read(P/'reservation.json')
def held():
 for n,ino in h['inodes'].items():
  p=R/'analysis/coordination-20261015'/n;assert p.stat().st_ino==ino and read(p)==h['identity']
held();D=R/'analysis/coordination-20261015/progress-dashboard';path=D/'functional-catalog.json';raw=path.read_bytes();old=json.loads(raw);data=copy.deepcopy(old)
points={m:read(R/f'releases/{m}/current.json')for m in ('online','local','launchers')};pins={m:sha(R/f'releases/{m}/current.json')for m in points}
assert points['online']['release']==RID and points['local']['release']=='local-'+RID and points['launchers']['V']==62
record=read(W/'delivery-result.json');git=read(W/'git-result.json');assert record['ok']and git['CI']=='success'
record=dict(record,source_PR=git['PR_number'],source_head=git['commit'],source_CI=git['CI'],Git_merge=False,evidence=[dict(path=str(W/n),sha256=sha(W/n))for n in ('delivery-result.json','actual-online-readback.json','installed-local-session.json','public-acceptance.json','public-native-verification.json','qa-cleanup-result.json','publication/launcher-local-verification.json','launcher-v62/qualification.json','launcher-v62/publication/installation.json')])
key='ring_cross_bag_actual_20261101';assert key not in data;data[key]=record
for m,row in data['catalog_pointers'].items():
 for k in row:row[k]=points[m][k]
data.update(release=RID,online_release=RID,local_release=points['local']['release'],online_manifest_sha=points['online']['manifest_sha256'],local_manifest_sha=points['local']['manifest_sha256'],local_manifest_sha256=points['local']['manifest_sha256'])
for k in ('manifest','manifest_sha','manifest_sha256'):data[k]=points['online']['manifest_sha256']
data.setdefault('launcher_delivery_history',[]).append(copy.deepcopy(data['current_launcher_delivery']))
data['current_launcher_delivery']=dict(record,release=points['launchers']['release'],launcher_release=points['launchers']['release'],launcher_V=62,V=62,launcher_sha256=points['launchers']['sha256'],sha256=points['launchers']['sha256'],delivery_complete=True,launcher_changed=True,signed_LOCAL_contains_current_raw_batch=True,Friends_payload_unchanged=True,normal_next_start_required=True,existing_upgrade_Run=True,current_signed_distribution_scope='V62分发戒指跨背包替换共享修复，保留商城、活动及126机关/150退场规则。')
card=next(c for c in data['systems']if c['id']=='inventory');note='普通与稀有时装跨背包替换已双端及V62修复，公网五戒指双向与冷登通过。'
assert len(note)<=64;card['summary_short']=note;card['current_delivery_note']=note;card.setdefault('delivery_history',[]).append(dict(release=RID,status='dual-installed-V62',scope=note,source_PR=git['PR_number'],source_head=git['commit'],Git_merge=False))
for scope in data['work_triage_registry']['current_delivered_test_scopes_by_item'].values():
 for m in scope['channels']:scope['current_pointer_sha256'][m]=pins[m]
 scope['evidence'].append(dict(role='current_pointer_inheritance',path=str(W/'delivery-result.json'),sha256=sha(W/'delivery-result.json')))
assert data['functional_stats']==old['functional_stats']and data['scoring']==old['scoring']and data['player_feedback_registry']==old['player_feedback_registry']
assert all(c['items']==o['items']and c['score']==o['score']and c.get('remaining_short')==o.get('remaining_short')for c,o in zip(data['systems'],old['systems']))
save(W/'progress-before.private.json',old);held();assert path.read_bytes()==raw and all(sha(R/f'releases/{m}/current.json')==v for m,v in pins.items())
temp=path.with_name('functional-catalog.ring-owned.tmp');assert not temp.exists();save(temp,data);os.replace(temp,path)
with(W/'progress-builder.log').open('xb')as log:q=subprocess.run([sys.executable,'-B','-X','utf8',D/'build_dashboard.py'],stdout=log,stderr=subprocess.STDOUT,timeout=240,creationflags=0x08000000)
assert q.returncode==0
published=read(D.parent/'progress-web-01a14442/latest-publication.json');assert published['ok']and published['public_hash_verified']and published['public_readback']['ok']and sha(published['path'])==published['sha256']==published['public_readback']['sha256']
html=Path(published['path']).read_text('utf-8-sig');actual=json.loads(re.search(r'const DATA=(.*?);\s*\nconst \$=',html,re.S).group(1).replace('<\\/','</'))
export=D.parent/'progress-web-01a14442/build_public.py';node=next(n for n in ast.walk(ast.parse(export.read_text('utf8')))if isinstance(n,ast.FunctionDef)and n.name=='public_metadata');ns={'re':re};exec(compile(ast.Module(body=[node],type_ignores=[]),str(export),'exec'),ns)
assert actual[key]==ns['public_metadata'](record)and actual['current_launcher_delivery']==ns['public_metadata'](data['current_launcher_delivery'])and actual['catalog_pointers']==data['catalog_pointers']and actual['functional_stats']==old['functional_stats']
held();save(W/'progress-readback.json',dict(ok=True,url=published['url'],html_sha256=published['sha256'],public_readback=published['public_readback'],scores_items_denominator_unchanged=True,unrelated_remaining_preserved=True,Git_merge=False))
print('Public progress published and exact sanitized data readback passed')
