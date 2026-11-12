"""Update the established dashboard only after both actual targets are accepted."""
from common import *
import copy,ssl,urllib.request
held()
for name in('unified-runtime-parity.json','qa-cleanup.json','new-schema-acceptance.json','online-public-acceptance.json','local-public-acceptance.json'):
    assert read(P/name)['ok'],name
pointers={ch:read(R/f'releases/{ch}/current.json')for ch in('online','local','launchers')}
assert pointers['online']['release']==RID and pointers['launchers']['V']==106
for channel in('online','local'):
    current=pointers[channel];value=copy.deepcopy(current)
    value.update(launcher_release=pointers['launchers']['release'],local_release=pointers['local']['release'],
        source_commit_url='https://github.com/641927456/els-server-collab/commit/'+plan['source_head'],
        source_merge_commit=None,source_Git_merged=False,Git_merge=False,current_delta_Git_merge=False)
    value.pop('source_issue',None)
    if channel=='online':
        assert read(P/'ordinary-entry-open.json')['ordinary_entry_open']
        value.update(ordinary_player_entry_open=True,maintenance_admission_closed=False)
    target=R/f'releases/{channel}/current.json';assert read(target)==current
    temporary=target.with_name('current.achievement-final.next');save(temporary,value);os.replace(temporary,target)
    pointers[channel]=value
directory=R/'analysis/coordination-20261015/progress-dashboard'
path=directory/'functional-catalog.json';raw=path.read_bytes();data=json.loads(raw);before=copy.deepcopy(data)
scoring=load('achievement_delivery_scoring',directory/'full_scope_scoring.py')
cards=load('achievement_delivery_cards',directory/'functional_cards.py');scoring.recount(before)
def leaves(d):return {i['id']:i for c in d['systems']for i in c['items']}
prior=leaves(before);weights={k:v['weight']for k,v in prior.items()}
for channel,row in data['catalog_pointers'].items():
    for key in row:row[key]=pointers[channel][key]
data.update(release=RID,online_release=RID,online_manifest_sha=pointers['online']['manifest_sha256'],online_runtime_files=pointers['online']['business_files_verified'])
data.update(local_release=pointers['local']['release'],local_manifest_sha=pointers['local']['manifest_sha256'],
    local_manifest_sha256=pointers['local']['manifest_sha256'],launcher=Path(pointers['launchers']['path']).name,
    launcher_release=pointers['launchers']['release'],paired_launcher=pointers['launchers']['release'],
    runtime_files=2875,local_runtime_files=2875,local_business_files=read(P/'unified-runtime-parity.json')['server_files'])
for key in('manifest','manifest_sha','manifest_sha256'):data[key]=pointers['online']['manifest_sha256']
summary='业绩已接47类来源、318条定义；新增公会徽章召唤、场景显示同步及原生战力业绩。'
remaining='其余13类来源、53组原奖励及自然GUI继续保留；缺失奖励暂缓发放。'
assert len(summary)<=64 and len(remaining)<=64
key='native_achievement_guild_banner_power_20261108_v1';assert key not in data
record=dict(online_installed=True,local_installed=True,launcher_installed=True,Git_submitted=True,Git_merge=False,
    source_PR=plan['source_PR'],source_head=plan['source_head'],launcher_V=106,connected_source_types=47,connected_definitions=318,
    total_definitions=377,remaining_source_types=13,original_reward_reference_groups=101,
    unresolved_original_reward_groups=53,item_reader_supported_reward_groups=50,
    missing_reward_substitution=False,panel_IP_hidden=True,same_server_source=True,same_signed_runtime=True,
    own_QA_cleaned=True,natural_GUI=False,natural_battle=False,summary=summary,remaining=remaining,
    online_observation_seconds=read(P/'online-installation-acceptance.json')['observation_seconds'],
    local_observation_seconds=read(P/'local-runtime-acceptance.json')['observation']['observation_seconds'])
data[key]=record
record.update(guild_banner_source=59,guild_banner_definitions=[350,351,352],guild_banner_display_paths=4,native_CP_source=17,native_CP_definitions=30,native_CP_thresholds=[4200,7000],native_CP_trust_human_approved=True,new_hook_sites=0,native_signed_component_loaded=True)
notes={'achievements.02':('已接47类来源、318条定义；新增公会徽章有效召唤计数、四处场景显示恢复及30条原生战力业绩。即时完成、账号共享、冷读、输入绑定、失败回滚和重复不增已核，保留此前有效来源。其余13类未接；原奖励101组有来源、50组有物品读取支持，53组缺失并暂缓。未按整项完成计分。',[])}
proof=dict(role='accepted_achievement_guild_banner_power_delivery',path=str(P/'unified-runtime-parity.json'),sha256=sha(P/'unified-runtime-parity.json'),source_PR=plan['source_PR'],source_head=plan['source_head'])
repairs={}
for identity,note in repairs.items():notes[identity]=(prior[identity]['note']+' '+note,[])
inheritance=dict(role='current_pointer_inheritance',path=str(P/'unified-runtime-parity.json'),sha256=sha(P/'unified-runtime-parity.json'))
for scope in data['work_triage_registry']['current_delivered_test_scopes_by_item'].values():
    for reference in scope['evidence']:assert sha(reference['path'])==reference['sha256']
    scope['current_pointer_sha256']={ch:sha(R/f'releases/{ch}/current.json')for ch in scope['channels']}
    scope['evidence'].append(inheritance)
data['current_pointer_refresh']=dict(scope='47 achievement source types including guild banner and native power; V106',
    pointers=copy.deepcopy(data['catalog_pointers']),delivery_key=key)
manifest=read(R/pointers['online']['path']/'rollup-manifest.json');modules={r['path']:r for r in manifest['files']}
for card in data['systems']:
    if card['id']=='achievements':
        card.setdefault('prior_delivery_descriptions',[]).append(dict(role='prior_delivery_description',summary=card['summary'],remaining=card['remaining']))
        card.update(summary=summary,summary_short=summary,remaining=remaining,remaining_short=remaining,
            readiness_label='限定来源和共享状态已交付；其余来源、奖励及自然GUI另列待办')
        card.setdefault('delivery_history',[]).append(dict(release=RID,channel='online+local+launcher',status='installed',scope=summary,natural_GUI=False,natural_battle=False))
    for item in card['items']:
        if item['id']not in notes:continue
        note,milestones=notes[item['id']]
        milestones=copy.deepcopy(prior[item['id']]['progress_milestones'])
        item.setdefault('prior_closure_notes',[]).append(dict(note=item['note'],progress_review=copy.deepcopy(item.get('progress_review'))))
        item.update(note=note,acceptance=note)
        if item['id']not in repairs:item['proof_level']='原生离线读取及双端实际协议存档；自然GUI及其余来源另待'
        item['progress_review']=dict(source_note_sha256=hashlib.sha256(note.encode()).hexdigest(),milestones=milestones,
            local_status='公会徽章、场景显示及战力业绩按实际同签名运行核收；其余范围保留',
            online_status='本批已安装且自有公网公会徽章、战力业绩及冷读核收；自然GUI未验',evidence=[proof],natural_GUI=False,natural_battle=False)
    for module in card.get('source_modules',[]):
        name=module['relative']
        if name in modules:module.update(path=str(R/pointers['online']['path']/name),sha256=modules[name]['sha256'],same_online_source=True)
scoring.recount(data);cards.validate(data);after=leaves(data)
assert {k:v['weight']for k,v in after.items()}==weights and data['milestones']==before['milestones']
assert data['player_feedback_registry']==before['player_feedback_registry']
for identity,item in prior.items():
    if identity not in notes:assert after[identity]['progress_milestones']==item['progress_milestones'],identity
save(P/'progress-before.private.json',before);assert path.read_bytes()==raw
tmp=path.with_name('functional-catalog.achievement-v106.next');save(tmp,data);os.replace(tmp,path)
with(P/'progress-builder.log').open('xb')as log:
    result=subprocess.run([sys.executable,'-B','-X','utf8',str(directory/'build_dashboard.py')],stdout=log,stderr=subprocess.STDOUT,timeout=240)
assert result.returncode==0,'Inspect progress-builder.log'
publication=read(directory.parent/'progress-web-01a14442/latest-publication.json');assert publication['ok']and publication['public_hash_verified']
url='https://134.175.57.52:80/els-progress/'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
with opener.open(urllib.request.Request(url,headers={'Cache-Control':'no-cache'}),timeout=20)as response:
    assert response.status==200;html=response.read()
assert hashlib.sha256(html).hexdigest()==publication['sha256']
line=next(line.strip()for line in html.decode('utf-8-sig').splitlines()if line.lstrip().startswith('const DATA='))
actual=json.loads(line.removeprefix('const DATA=').removesuffix(';').replace('<'+chr(92)+'/','</'))
assert actual[key]==record and actual['catalog_pointers']==data['catalog_pointers']
save(P/'progress-readback.json',dict(ok=True,url=url,html_sha256=publication['sha256'],record=record,
    updated_cards=['achievements'],reviewed_items=sorted(notes),weights_and_function_set_unchanged=True,
    unrelated_milestones_unchanged=True,natural_live_acceptance_not_scored=True,
    whole_authority_and_BUFF_implementation_not_scored=True))
print(json.dumps(dict(ok=True,public_progress_readback=True,updated_cards=1,reviewed_items=len(notes),unrelated_milestones_unchanged=True)))
