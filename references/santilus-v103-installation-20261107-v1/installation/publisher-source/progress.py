"""Update the existing progress catalogue without changing any scores."""
from common import *
import copy,ssl,urllib.request
held();D=R/'analysis/coordination-20261015/progress-dashboard';path=D/'functional-catalog.json'
raw=path.read_bytes();data=json.loads(raw);old=copy.deepcopy(data)
stage=sys.argv[1];assert stage in('merged','installed')
git=read(P/'git.json')
record=dict(source_PR=git['PR'],source_head=git['head'],source_merge_commit=git['merge_commit'],Git_merge=True,
 summary='33242召唤及控制器退场修复已合并；安装分别核收。',
 remaining='原生序号归因、旧游标及第三阶段清场仍待核。',
 online_installed=False,local_installed=False,launcher_installed=False,
 natural_GUI=False,natural_battle=False)
if stage=='installed':
 receipt=read(P/'final-three-channel-acceptance.json');assert receipt['ok']
 record.update(online_installed=True,local_installed=True,launcher_installed=True,
  summary='33242召唤及退场修复已安装双端，签名同源。',
  remaining='原生15秒心跳发送待归因；1395清场待修；旧游标为自有QA。')
 for channel,row in data['catalog_pointers'].items():
  pointer=read(R/'releases'/channel/'current.json')
  for key in row:row[key]=pointer[key]
 online=read(R/'releases/online/current.json');local=read(R/'releases/local/current.json');launcher=read(R/'releases/launchers/current.json')
 data.update(release=online['release'],online_release=online['release'],online_manifest_sha=online['manifest_sha256'],
  online_runtime_files=online['business_files_verified'],local_release=local['release'],
  local_manifest_sha=local['manifest_sha256'],local_manifest_sha256=local['manifest_sha256'],
  launcher=Path(launcher['path']).name,launcher_release=launcher['release'],paired_launcher=launcher['release'],
  runtime_files=launcher['payload_files_verified'],local_runtime_files=launcher['payload_files_verified'])
 data['local_business_files']=read(P/'unified-runtime-parity.json')['server_files']
 for k in('manifest','manifest_sha','manifest_sha256'):data[k]=online['manifest_sha256']
assert len(record['summary'])<=64 and len(record['remaining'])<=64
key='santilus_lifecycle_20261107_v1';data[key]=record
if stage=='installed':
 source=R/online['path'];rows={row['path']:row for row in read(source/'rollup-manifest.json')['files']}
 for card in data['systems']:
  for module in card.get('source_modules',[]):
   name=module['relative']
   if name in rows:module.update(path=str(source/name),sha256=rows[name]['sha256'],same_online_source=True)
 proof=dict(role='current_pointer_inheritance',path=str(P/'unified-runtime-parity.json'),sha256=sha(P/'unified-runtime-parity.json'))
 for item in data['work_triage_registry']['current_delivered_test_scopes_by_item'].values():
  item['current_pointer_sha256']={channel:sha(R/'releases'/channel/'current.json')for channel in item['channels']}
  item['evidence'].append(proof)
 data['current_pointer_refresh']=dict(scope='Integrated quest inventory dungeon and raid repairs',pointers=copy.deepcopy(data['catalog_pointers']),delivery_key=key)
else:assert data['systems']==old['systems']
assert data['functional_stats']==old['functional_stats']
save(P/('progress-before-'+stage+'.private.json'),old);assert path.read_bytes()==raw
temporary=path.with_name('functional-catalog.capacity.next');save(temporary,data);os.replace(temporary,path)
with(P/('progress-builder-'+stage+'.log')).open('xb')as log:
 result=subprocess.run([sys.executable,'-B','-X','utf8',str(D/'build_dashboard.py')],stdout=log,stderr=subprocess.STDOUT,timeout=240)
assert result.returncode==0,'Inspect builder log'
published=read(D.parent/'progress-web-01a14442/latest-publication.json');assert published['ok'] and published['public_hash_verified']
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
with opener.open(urllib.request.Request('https://134.175.57.52:80/els-progress/',headers={'Cache-Control':'no-cache'}),timeout=20)as response:html=response.read()
assert hashlib.sha256(html).hexdigest()==published['sha256']
line=next(line.strip()for line in html.decode('utf-8-sig').splitlines()if line.lstrip().startswith('const DATA='))
actual=json.loads(line.removeprefix('const DATA=').removesuffix(';').replace('<'+chr(92)+'/','</'))
assert actual[key]==record and actual['functional_stats']==data['functional_stats']
save(P/('progress-'+stage+'-readback.json'),dict(ok=True,html_sha256=published['sha256'],record=record,scores_unchanged=True))
print(json.dumps(dict(ok=True,stage=stage,public_hash_verified=True,scores_unchanged=True)))
