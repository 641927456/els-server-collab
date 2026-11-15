from pathlib import Path
import hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
source=ROOT/'analysis/pr771-remaining-20261103-v1/resources/RidingPetRacingData.lua.tables.json'
calls=json.loads(source.read_bytes())['__symbolic_calls__']
names={'AddStartBoosterTemplate':'start','AddBoosterTemplate':'normal','AddBreakThroughBoosterTemplate':'obstacle','AddFinalSpurtBoosterTemplate':'spurt'}
data=dict(schema_version=1,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),boosters={},obstacles=[])
for c in calls:
    name=c['function'].split('.')[-1]
    if name=='SetRidingPetRacingData':
        p=c['arguments'][1];data['race']={k:p[k]for k in ('FinishLineTime','BoosterCooltime','StartCountStateTime','AllFinishStateTime','AutoLeaveTime','FinalSpurtStartStopTime')}
    elif name in names:
        p=c['arguments'][1];q={k:v for k,v in p.items()if type(v)in(int,float)}
        if 'Obstacle_CanJump'in p:q['Obstacle_CanJump']=p['Obstacle_CanJump']['global']=='TRUE'
        data['boosters'].setdefault(names[name],[]).append(q)
    elif name=='AddObstacleTemplate':
        p=c['arguments'][1];data['obstacles'].append({k:p[k]for k in ('StartTime','TopTime','BottomTime','TopYPos')})
target=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime/els_server/data/mount_racing_physics.json'
target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(dict(path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
