"""Finite Lithia finale compatibility; retail proximity semantics remain unknown."""
import functools,hashlib,json

DUNGEONS=(35320,35321,35322)
SCRIPT='LITHIA_MEMORY8_BOSS_END.lua'
SCRIPT_SHA='ff369045cbead25cd5951eb7385f73e8ff0e575e2daed5fb4055ace5d05f9ae2'
FIND={'m_iID':28560,'m_eClearType':27,'m_bAutomaticDescription':0,
      'm_ClearCondition':{'m_eDungeonID':{'0':None,'1':35320,'2':35321,'3':35322},'m_eFindNPCID':{'0':None,'1':9431}}}
RECEIPTS={qid:{'m_iID':qid,'m_eClearType':80,'m_bAutomaticDescription':0,
              'm_ClearCondition':{'m_iClearCount':1,'m_eQuestID':{'0':None,'1':qid-10}}} for qid in (28570,28580)}

def target(sub):
    if sub!=FIND and sub not in RECEIPTS.values():raise ValueError('Unsupported finale objective')
    return 1

def receipt_progress(sub,completed):
    if sub not in RECEIPTS.values():raise ValueError('Unsupported finale completion receipt')
    return int(sub['m_iID']-10 in completed)

@functools.lru_cache(maxsize=1)
def sources():
    from els_server.game_data import client_data
    from els_server.domain.dungeon_routes import route_catalog
    routes=route_catalog();native=client_data().npc(9455);result={}
    if (routes.manifest['source_sha256'].get(SCRIPT)!=SCRIPT_SHA or native['script']!=SCRIPT
        or native['class_id']!=103 or native['is_npc'] is not True):raise ValueError('Finale scripted actor identity')
    for dungeon in DUNGEONS:
        graph=routes.graph(dungeon);found=[];ends=[]
        for stage,row in graph['stages'].items():
            for part,data in row['parts'].items():
                for group in data['groups']:
                    for actor in group['npcs']:
                        if actor.get('template')==9431:found.append((int(stage),int(part),actor))
                        if actor.get('template')==9455:ends.append(actor)
        if (len(found)!=1 or found[0][:2]!=({35320:3,35321:2,35322:0}[dungeon],0) or found[0][2]['active'] is not True
            or found[0][2].get('ally') or found[0][2].get('team')!=1
            or len(ends)!=1 or ends[0]['active'] is not False or ends[0].get('ally') or ends[0].get('team')!=1):
            raise ValueError('Finale original graph actors')
        result[dungeon]=(graph,found[0])
    return result

def inactive_quest(dungeon,npc):
    return 28610 if dungeon in DUNGEONS and npc==9455 and dungeon in sources() else None

def playing_owner(s):
    """Bind current root/cache and authenticated playing connection before observing."""
    account=s.account;root=account.root;uid=account.uid
    if (account.store is None or account.store.uid!=uid or root.character_accounts.get(uid) is not account
        or account.account_id!=root.account_id or account.characters is not root.characters):return None
    app=getattr(s,'application',None)
    if app is not None:
        identity=getattr(s,'identity',{})
        if (getattr(s,'released',True) or identity.get('id')!=account.account_id
            or app.accounts.get(account.account_id) is not root or app.playing.get(account.account_id) is not s
            or not app.registry.enabled(account.account_id)):return None
    character=account.character()
    if character is None or character['uid']!=uid or character['unit_type']!=15:return None
    return (str(account.store.path),account.account_id,uid,s.shop_session_id,id(root),id(account))

def encounter(s,run,state):
    """Observe a live source actor after current-part ACK; never change the run."""
    if (s.role!='game' or s.phase!='dungeon_active' or not s.dungeon_substage_synced
        or run is None or run is not s.dungeon_run or run.identity not in DUNGEONS
        or s.dungeon_id!=run.identity or s.reward_run_id!=run.run_id or run.started_at is None):return None
    owner=playing_owner(s)
    if owner is None:return None
    active=next((row for row in state['active'] if row['id']==28560),None)
    if active is None or active['objectives'].get(28560)!=0:return None
    graph,(stage,part,source)=sources()[run.identity]
    if (run.graph!=graph or (run.stage,run.part)!=(stage,part) or type(run.visits) is not int or run.visits<1):return None
    actors=[n for n in run.current['npcs'] if n.get('template')==9431]
    if len(actors)!=1:return None
    actor=actors[0];key=actor.get('key')
    if (type(key) is not int or key<0 or key in run.defeated
        or any(actor.get(k)!=v for k,v in source.items())):return None
    evidence=dict(owner=list(owner),run=run.run_id,source=graph['source_sha256'],stage=stage,part=part,
                  visits=run.visits,key=key,source_index=source['source_index'],quest=28560,
                  generation=active['generation'],accepted_at=active['accepted_at'],
                  acceptance_epoch=getattr(s,'_quest_discovery_epoch',0))
    raw=json.dumps(evidence,sort_keys=True,separators=(',',':')).encode()
    digest=hashlib.sha256(raw).hexdigest()
    event=dict(kind='visit_dungeon',dungeon=run.identity,level=s.account.character()['level'],
               finale_find=dict(policy='loaded-source-actor-v1',npc=9431,evidence=evidence,digest=digest))
    return ('finale-find:'+digest,event,raw)

def find_increment(sub,event):
    if sub!=FIND or event.get('kind')!='visit_dungeon' or event.get('dungeon') not in DUNGEONS:return 0
    witness=event.get('finale_find')
    if not isinstance(witness,dict) or set(witness)!={'policy','npc','evidence','digest'}:return 0
    evidence=witness['evidence']
    if not isinstance(evidence,dict) or set(evidence)!={'owner','run','source','stage','part','visits','key','source_index','quest','generation','accepted_at','acceptance_epoch'}:return 0
    raw=json.dumps(evidence,sort_keys=True,separators=(',',':')).encode()
    return int(witness['policy']=='loaded-source-actor-v1' and witness['npc']==9431
               and witness['digest']==hashlib.sha256(raw).hexdigest() and evidence['quest']==28560
               and (evidence['stage'],evidence['part'])==sources()[event['dungeon']][1][:2] and evidence['source_index']==1
               and evidence['source']==sources()[event['dungeon']][0]['source_sha256'])
