"""Finite original town NPC objectives; no wildcard quest admission."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

QUEST=13
NPC=10018
QUEST_IDS=frozenset((13, 6160, 6190, 6220, 7290, 7320, 7360, 26830, 26880, 100050, 100060, 100080, 100130, 100160, 100190, 100210, 100240, 100250, 100260, 100270, 100280, 100330, 100340, 100360, 100410, 100420, 100440, 100470, 100480, 100500, 100520, 100540, 100550, 100560, 100590, 100600, 100620, 100630, 100660, 100680, 100690, 100710, 100730, 100750, 100770, 100790, 100800, 100840, 100850, 100870, 100900, 100910, 100920, 100940, 100950, 100970, 100980, 100990, 101010, 101020, 101030, 101040))
SUBQUEST_IDS=frozenset((13, 6160, 6190, 6220, 7290, 7320, 7360, 22313, 22333, 26830, 26870, 100050, 100060, 100080, 100130, 100160, 100190, 100210, 100240, 100250, 100260, 100270, 100280, 100330, 100340, 100360, 100410, 100420, 100440, 100470, 100480, 100500, 100520, 100540, 100550, 100560, 100590, 100600, 100620, 100630, 100660, 100680, 100690, 100710, 100730, 100750, 100770, 100790, 100800, 100840, 100850, 100870, 100900, 100910, 100920, 100950, 100970, 100990, 101030, 101040))
EARLY_EPIC_BINDINGS={100050:(10005,40005),100060:(10006,40006),100080:(10005,40005)}

@functools.lru_cache(maxsize=1)
def catalog():
    path=PROJECT_ROOT/'els_server/data/town_dialogue_quests.json'
    raw=path.read_bytes();row=json.loads(raw)
    manifest=json.loads(path.with_suffix('.manifest.json').read_bytes());data=client_data()
    if (row['schema_version']!=2 or manifest['schema_version']!=2
        or row['client_sha256']!=CLIENT_SHA or manifest['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']
        or row['catalog_sha256']!=data.manifest['catalog_sha256']
        or {int(k) for k in row['quests']}!=QUEST_IDS or {int(k) for k in row['subquests']}!=SUBQUEST_IDS
        or row['npc']!=NPC or row['house']!=40017
        or manifest['quests']!=62 or manifest['subquests']!=60):raise ValueError('Town dialogue catalog identity')
    from els_server.storage.local_state import TOWN_SCENES
    if len(row['towns'])!=14 or any(TOWN_SCENES.get(int(town))!=scene for town,scene in row['towns'].items()):raise ValueError('Town dialogue scene identity')
    if set(row['npc_bindings'])!={'10010', '10005', '10006', '10030', '10071', '10018', '10056', '10015', '10078', '10040', '10020', '10145', '10001', '10029', '10067', '10144', '10012', '10021', '10002', '10057', '10039', '10000', '10143', '10363'}:raise ValueError('Town dialogue NPC set')
    for binding in row['npc_bindings'].values():
        if not binding['houses'] or not binding['towns'] or any(TOWN_SCENES.get(int(t))!=scene for t,scene in binding['towns'].items()):raise ValueError('Town dialogue NPC scene source')
    for key,sub in row['subquests'].items():
        if (sub['m_iID']!=int(key) or sub['m_eClearType']!=1 or set(sub['m_ClearCondition'])!={'m_eTalkNPCID'}
            or str(sub['m_ClearCondition']['m_eTalkNPCID']) not in row['npc_bindings']):raise ValueError('Town dialogue exact objective source')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES
    from els_server.domain.acquisition_policy import require_acquirable
    if {r['template'] for r in row['reward_definitions']}!={109955, 118149, 92111, 710160, 92112, 710098, 92115, 78996, 78999, 79063, 79064, 79065, 77090, 30577, 77110, 131641, 131642, 131643, 131644, 131645, 163135}:raise ValueError('Town dialogue reward set')
    for item in row['reward_definitions']:
        template=item['template'];require_acquirable(template)
        if template not in VERIFIED_TEMPLATES or hashlib.sha256(data.item(template)['record']).hexdigest()!=item['record_sha256']:raise ValueError('Town dialogue reward identity')
    for identity,(npc,house) in EARLY_EPIC_BINDINGS.items():
        if (row['quests'][str(identity)]['m_eQuestType']!=5
            or row['npc_bindings'][str(npc)]!=dict(houses=[house],towns={'20001':263})
            or row['subquests'][str(identity)]!=dict(m_iID=identity,m_eClearType=1,m_bAutomaticDescription=0,
                                                    m_ClearCondition=dict(m_eTalkNPCID=npc))):
            raise ValueError('Early Epic NPC source identity')
    # Exact source bindings for the four newly admitted Epic NPC links.
    for identity,npc,house,town,scene in [(100130, 10010, 40009, 20002, 262), (100160, 10012, 40012, 20003, 265), (100190, 10012, 40012, 20003, 265), (100210, 10015, 40013, 20003, 265)]:
        if (row['quests'][str(identity)]['m_eQuestType']!=5
            or row['npc_bindings'][str(npc)]!=dict(houses=[house],towns={str(town):scene})
            or row['subquests'][str(identity)]['m_ClearCondition']!=dict(m_eTalkNPCID=npc)):
            raise ValueError('Mid-story NPC source identity')
    if row['npc_bindings']['10363']!=dict(houses=[40263],towns={'20012':1004}):raise ValueError('Noah diary exact scene binding')
    from els_server.domain.job_quests import extend_town_dialogue
    return extend_town_dialogue(row)

def target(sub):
    if sub!=catalog()['subquests'].get(str(sub.get('m_iID'))):raise ValueError('Unsupported town NPC dialogue objective')
    return 1

def handle(s,event,sequence):
    from els_server.protocol import tutorial_dialogue_messages as wire
    from els_server.protocol.quest_messages import QUEST_REQUIREMENTS_NOT_MET,QUEST_REWARD_UNAVAILABLE
    if event.event_id!=0x202 or event.kind!=0xfd:return None
    try:npc=wire.request(event.payload)
    except ValueError:return [wire.acknowledgement(result=QUEST_REWARD_UNAVAILABLE)]
    binding=catalog()['npc_bindings'].get(str(npc))
    if binding is None:return None
    if (s.role!='game' or s.phase!='town_ready' or str(s.active_map) not in binding['towns']
        or s.account.get_location()['map']!=s.active_map or type(sequence) is not int or not 1<=sequence<2**32
        or event.performers!=(0,) or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff
        or event.payload_mode!=0):return [wire.acknowledgement(result=QUEST_REQUIREMENTS_NOT_MET)]
    from els_server.storage.town_dialogue import interact
    from els_server.domain.quest_flow import store
    operation=s.shop_session_id+':town-npc-talk:'+str(s.account.uid)+':'+str(sequence)
    try:return interact(store(s),npc,operation)
    except ValueError:return [wire.acknowledgement(result=QUEST_REQUIREMENTS_NOT_MET)]
