"""Freeze the reviewed mentor overlay on the immutable, uninstalled duel base."""
from pathlib import Path
import ast,copy,hashlib,json,os,shutil
W=Path(__file__).resolve().parent;D=W.parent/'duel-wire-v2';C=W/'candidate';B=D/'full-source'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
old=read(D/'delivery-manifest.json');previous={r['path']:r for r in old['files']}
rows=[];dependencies=[]
for p in sorted((C/'els_server').rglob('*')):
    if not p.is_file():continue
    name=p.relative_to(C).as_posix();digest=sha(p)
    if p.suffix=='.py':ast.parse(p.read_bytes())
    row=dict(path=name,size=p.stat().st_size,sha256=digest,base_sha256=previous.get(name,{}).get('sha256'))
    (dependencies if digest==row['base_sha256']else rows).append(row)
assert len(rows)==36 and sum(r['base_sha256']is None for r in rows)==13 and len(dependencies)==3
proof_names=['public-info-native-1793906750003934600.json','search-native-1793908663618809500.json',
 'summon-native-1793910008322049400.json','rewards-native-1793911858551878900.json',
 'blessing-native-1793913919600762600.json','relation-storage-1793907253154738100.json',
 'storage-edges-1793908608792218500.json','relation-tls-1793907877310702600.json',
 'relation-edges-tls-1793909054974636900.json','summon-tls-1793910141787571100.json',
 'party-play-tls-1793911001050060200.json','graduation-tls-1793911551658265200.json',
 'quest-tls-1793912657563205900.json','boxes-tls-1793913014193230200.json',
 'pending-teacher-tls-1793915129701251100.json','duel-tasks-tls-1793914849266878400.json',
 'luciel-box-tls-1793915003937548100.json','clear-tasks-tls-1793914434119152300.json',
 'black-gate-tasks-tls-1793914598370397600.json','blessing-tls-1793914504026988200.json']
evidence=[]
for name in proof_names:
    p=W/name;value=read(p);assert value['ok']and not value.get('worker_errors'),name
    evidence.append(dict(path=str(p),sha256=sha(p),ok=True,checks=value.get('checks',[])))
review=dict(ok=True,reviewed=True,scope='原生师徒关系、寻找/召唤、组队XP/疲劳、14任务及道具使用、转职证明和出师',
    files=rows,source_parent=dict(path=str(B),manifest_sha256=sha(D/'delivery-manifest.json'),installed=False),
    related_successes_reused=True,line_ending_AST_reuse=read(W/'line-ending-normalization.json'),evidence=evidence,
    fixed_findings=[
      '被动邀请方旧presence签名没有关系，登出后在线状态未退役；改为读取其当前保存关系。',
      '零疲劳组队串行进入时后续成员资格重算失真；复用同一批实际准入结果。',
      '同批共享结算升级后分段通知仍持有旧等级活动身份；通知输出前沿现有时钟重读，实际三人升级通关验证。',
      '复活石箱误走空背包奖励列表；复用现有角色计数及原生197。',
      '转职证明被动收件人不应使用玩家主动操作的待删除限制；教师待删除不阻断徒弟转职，实际删除/恢复API验证。'],
    boundaries=dict(installed=False,main_merged=False,launcher_updated=False,public_progress_updated=False,
        original_Game_mentor_case=False,natural_GUI=False,all_feature_groups_complete=False,
        original_EXE_KOM_modified=False,new_production_hook=False,player_database_restore=False,
        test_elapsed_time_and_source_fixtures_explicit=True),
    new_lazy_tables=['native_mentor_relations','native_mentor_operations','native_mentor_search_times','native_mentor_graduations',
        'native_mentor_quest_cycles','native_mentor_quest_operations','native_mentor_quest_history','native_mentor_quest_facts',
        'native_mentor_career_rewards','character_mentor_resonance_period'],install_DDL_statements=0)
save(W/'review-verification.json',review)
full=W/'full-source';assert not full.exists();full.mkdir()
for row in old['files']:
    p=B/row['path'];assert p.stat().st_size==row['size']and sha(p)==row['sha256'],row['path']
    t=full/row['path'];t.parent.mkdir(parents=True,exist_ok=True);os.link(p,t)
files=dict(previous)
for row in rows:
    t=full/row['path'];t.parent.mkdir(parents=True,exist_ok=True)
    if t.exists():t.unlink()
    shutil.copyfile(C/row['path'],t)
    files[row['path']]={k:row[k]for k in('path','size','sha256')}
manifest=copy.deepcopy(old);manifest.update(release='native-mentor-closure-20261106-v1',
    path='releases/online/native-mentor-closure-20261106-v1',parent_release=old['release'],
    parent_manifest_sha256=sha(D/'delivery-manifest.json'),files=[files[n]for n in sorted(files)],file_count=len(files))
save(W/'delivery-manifest.json',manifest)
save(W/'candidate-manifest.json',dict(parent=review['source_parent'],files=rows,unchanged_dependencies=dependencies))
save(W/'candidate-source-binding.json',dict(ok=True,source_frozen=True,full_source=str(full),
    manifest_sha256=sha(W/'delivery-manifest.json'),review_sha256=sha(W/'review-verification.json'),
    source_delta=36,new_files=13,files=len(files),client_support_delta=0,
    base_duel_PR=885,base_duel_head='35cc34e6e1424135dc11c6bfd9e96450c8b61a00',
    native_Game_mentor_qualified=False,installed=False,publication_hold='Performance peer final handoff and installer GM/event preservation fix; merge this overlay into that final baseline before installing'))
print(json.dumps(dict(ok=True,source_delta=36,new_files=13,files=len(files),installed=False)))
