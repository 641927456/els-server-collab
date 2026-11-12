"""Bind the frozen mentor revision to scoped reused results and actual Game QA."""
from pathlib import Path
import copy,hashlib,json
W=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
binding=read(W/'candidate-source-binding-v5.json');manifest=read(W/'candidate-manifest-v5.json')
for row in manifest['files']:
    assert sha(W/'candidate-v5'/row['path'])==row['sha256']==sha(W/'full-source-v5'/row['path'])
review=copy.deepcopy(read(W/'review-verification.json'))
review.update(scope=review['scope']+'；原生10项设置持久化及好友/师徒共享2F冷登初始化',files=manifest['files'],
    source_snapshot=str(W/'full-source-v5'),source_manifest_sha256=sha(W/'delivery-manifest-v5.json'))
review['evidence']=[row for row in review['evidence']if Path(row['path']).name!='summon-tls-1793910141787571100.json']
new=['summon-direct-tls-1793918842826968300.json','social-settings-native-1793917236428954500.json','social-settings-native-save-1793917689126080500.json',
 'social-settings-tls-1793917244974160500.json','mentor-initialization-native-1793918161882744200.json',
 'mentor-initialization-tls-1793918170205729500.json','native-game-qualification-v5.json']
for name in new:
    p=W/name;v=read(p);assert v['ok']and not v.get('worker_errors'),name
    review['evidence'].append(dict(path=str(p),sha256=sha(p),ok=True,checks=v.get('checks',v.get('cases',[]))))
review['fixed_findings']+=['原生2F设置字节原为全零，客户端在同意前自动拒绝师徒邀请；第8项正确初始化，完整167/168保存并在重登恢复。',
 '冷登伙伴沿原生2F/DD90A0记录恢复；与现有好友投影在同一组包入口构造，保留好友、分组、其他字段与实际健康数据。']
review['fixed_findings'].append('原始720成功消费者直接发送227，旧服务端错误要求225；复用现有城镇准入和到达保存，删去无依据的普通225中转。')
review['new_lazy_tables'].append('native_social_settings')
review['boundaries'].update(original_Game_mentor_case=True,natural_GUI=False)
review['reviewed_native_failures_retained']=['native-game-invitation-partial-v6.json','native-game-cold-failure-v7.json',
 'mentor-initialization-tls-1793918025159422600.json','native-game-direct-arrival-failure-v9.json']
review['observer_timing_correction']=read(W/'native-observer-correction-v9.json')
review['reuse_mapping']=dict(native_v6_invitation='same original consumer/producer and source section; v5 empty-relation2F is byte-identical to v2',
 settings_v2='same three settings modules,167 routing,2F option bytes and mentor recipient gate',
 v1_economy='no changed reward/quest/party/XP/fatigue/mail or storage sections; 19 unchanged scoped results retained; old225 summon test replaced with direct227 case',
 native_v5='actual cold partner and cross-Town summon with original callbacks and125s after original direct227 arrival')
save(W/'review-verification-v5.json',review)
save(W/'final-source-binding-v5.json',dict(ok=True,source_frozen=True,full_source=str(W/'full-source-v5'),
    source_delta=42,new_files=16,files=1594,client_support_delta=0,installed=False,main_merged=False,
    candidate_binding_sha256=sha(W/'candidate-source-binding-v5.json'),manifest_sha256=sha(W/'delivery-manifest-v5.json'),
    review_sha256=sha(W/'review-verification-v5.json'),native_game_qualified=True,natural_GUI=False,
    actual_Game_scope='One original teacher and one explicit protocol pupil; v6 original invitation/answer reused; v5 cold partner and cross-Town summon',
    publication_hold='Performance peer final handoff and reviewed installer GM/event preservation correction; integrate final baseline before installing'))
print(json.dumps(dict(reviewed=True,source_delta=42,related_results=len(review['evidence']),native_game_qualified=True,installed=False)))
