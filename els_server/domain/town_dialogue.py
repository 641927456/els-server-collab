"""Finite original town NPC objectives; no wildcard quest admission."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

QUEST=13
NPC=10018
QUEST_IDS=frozenset((13, 6160, 6190, 6220, 7290, 7320, 7360, 22349, 22350, 22352, 22353, 22355, 22357, 22359, 22360, 22361, 22363, 22365, 22367, 22369, 22370, 22372, 22373, 22378, 22390, 22420, 22450, 22460, 22480, 22490, 22510, 22520, 22540, 22560, 22570, 22920, 23090, 23120, 23150, 23180, 23210, 23240, 23270, 23300, 23430, 23440, 23490, 23520, 23530, 23550, 23560, 23580, 23610, 23620, 23640, 23650, 23660, 23670, 23690, 23700, 23740, 23750, 23760, 23770, 23780, 24030, 24040, 24050, 24060, 24110, 24111, 24120, 24170, 24220, 24230, 24320, 24330, 24350, 24360, 24370, 24380, 24390, 24460, 24470, 24480, 24490, 24600, 24610, 24620, 24691, 24692, 24693, 24694, 24695, 24696, 24705, 24709, 24713, 24714, 24718, 24719, 24720, 24721, 24722, 24723, 24729, 24730, 24731, 24732, 24739, 24740, 24741, 24754, 24755, 24756, 24757, 24758, 24759, 24776, 24777, 24778, 24779, 24780, 24781, 24782, 24783, 24784, 24785, 24806, 24807, 24808, 24809, 24810, 24811, 24812, 24813, 24814, 24819, 24820, 24821, 24826, 24827, 24828, 24829, 24830, 24831, 24836, 24837, 24838, 24839, 24850, 24851, 24852, 25500, 25510, 26750, 26780, 26830, 26880, 26930, 27060, 27100, 27190, 27260, 27270, 27340, 27400, 27440, 27460, 28710, 28720, 28730, 28740, 28780, 28800, 100050, 100060, 100080, 100130, 100160, 100190, 100210, 100240, 100250, 100260, 100270, 100280, 100330, 100340, 100360, 100410, 100420, 100440, 100470, 100480, 100500, 100520, 100540, 100550, 100560, 100590, 100600, 100620, 100630, 100660, 100680, 100690, 100710, 100730, 100750, 100770, 100790, 100800, 100840, 100850, 100870, 100900, 100910, 100920, 100940, 100950, 100970, 100980, 100990, 101010, 101020, 101030, 101040))
SUBQUEST_IDS=frozenset((13, 6160, 6190, 6220, 7290, 7320, 7360, 22313, 22315, 22333, 22350, 22354, 22540, 23090, 23550, 24030, 24040, 24050, 24060, 24110, 24111, 24120, 24170, 24220, 24230, 24320, 24330, 24350, 24360, 24370, 24380, 24390, 24460, 24470, 24480, 24490, 24600, 24610, 24620, 24690, 24820, 25500, 25510, 26750, 26830, 26870, 26930, 27060, 27100, 27190, 27260, 27270, 27340, 27400, 27440, 27460, 28720, 42511, 100050, 100060, 100080, 100130, 100160, 100190, 100210, 100240, 100250, 100260, 100270, 100280, 100330, 100340, 100360, 100410, 100420, 100440, 100470, 100480, 100500, 100520, 100540, 100550, 100560, 100590, 100600, 100620, 100630, 100660, 100680, 100690, 100710, 100730, 100750, 100770, 100790, 100800, 100840, 100850, 100870, 100900, 100910, 100920, 100950, 100970, 100990, 101030, 101040, 162120))
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
        or manifest['quests']!=228 or manifest['subquests']!=108):raise ValueError('Town dialogue catalog identity')
    from els_server.storage.local_state import TOWN_SCENES
    if len(row['towns'])!=16 or any(TOWN_SCENES.get(int(town))!=scene for town,scene in row['towns'].items()):raise ValueError('Town dialogue scene identity')
    if set(row['npc_bindings'])!={'10500', '10056', '10021', '10227', '10001', '10145', '10029', '10228', '10012', '10229', '10026', '10005', '10363', '10030', '10071', '10231', '10222', '10002', '10025', '10381', '10040', '10006', '10424', '10000', '10020', '10067', '10057', '10144', '10015', '10039', '10230', '10078', '10235', '10010', '10360', '10018', '10143'}:raise ValueError('Town dialogue NPC set')
    for binding in row['npc_bindings'].values():
        if not binding['houses'] or not binding['towns'] or any(TOWN_SCENES.get(int(t))!=scene for t,scene in binding['towns'].items()):raise ValueError('Town dialogue NPC scene source')
    for key,sub in row['subquests'].items():
        if (sub['m_iID']!=int(key) or sub['m_eClearType']!=1 or set(sub['m_ClearCondition'])!={'m_eTalkNPCID'}
            or str(sub['m_ClearCondition']['m_eTalkNPCID']) not in row['npc_bindings']):raise ValueError('Town dialogue exact objective source')
    if (row['npc_bindings']['10025']!=dict(houses=[40028],towns={'1009':851,'20010':778})
        or row['subquests']['162120']!=dict(m_iID=162120,m_eClearType=1,m_bAutomaticDescription=0,
                                          m_ClearCondition=dict(m_eTalkNPCID=10025))
        or any(row['quests'][str(q)]['m_eQuestType']!=5 for q in (22378,22390,22420))):
        raise ValueError('Varnimyr NPC10025 source identity')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES
    from els_server.domain.acquisition_policy import require_acquirable
    if {r['template'] for r in row['reward_definitions']}!={109955, 118149, 710160, 78996, 78999, 77090, 77110, 131641, 131642, 131643, 131644, 131645, 713275, 163135, 92111, 92112, 710098, 92115, 79063, 79064, 79065, 136034, 136039, 30577, 109945}:raise ValueError('Town dialogue reward set')
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
    for identity,npc,house in ((25500,10230,40176),(25510,10231,40177)):
        quest=row['quests'][str(identity)]
        if (quest['m_eQuestType']!=5 or quest['QuestCondition']['m_iLevel']!=99
            or quest['QuestCondition']['m_eUnitType']!={'1':13}
            or row['subquests'][str(identity)]!=dict(m_iID=identity,m_eClearType=1,m_bAutomaticDescription=0,m_ClearCondition=dict(m_eTalkNPCID=npc))
            or row['npc_bindings'][str(npc)]!=dict(houses=[house],towns={'20010':778})):
            raise ValueError('Laby99 NPC exact source identity')
    for identity,npc in ((27190, 10228), (27260, 10227), (27270, 10231), (27340, 10230), (27400, 10227), (27440, 10227), (27460, 10227)):
        quest=row['quests'][str(identity)]
        if (quest['m_eQuestType']!=5 or quest['QuestCondition']['m_iLevel']!=99
            or quest['QuestCondition']['m_eUnitType']!={'1':14}
            or row['subquests'][str(identity)]!=dict(m_iID=identity,m_eClearType=1,m_bAutomaticDescription=0,m_ClearCondition=dict(m_eTalkNPCID=npc))
            or row['npc_bindings'][str(npc)]!=dict(houses=[{10227:40173,10228:40174,10230:40176,10231:40177}[npc]],towns={'20010':778})):
            raise ValueError('Noah99 NPC exact source identity')
    # Original ordinary-role Elysion chapter dialogue gaps, bounded to the
    # already-qualified source houses. No new NPC location wildcard.
    for identity in (22349,22350):
        quest=row['quests'][str(identity)]
        if (quest['m_eQuestType']!=5 or quest['QuestCondition']['m_iLevel']!=99
            or set(quest['QuestCondition']['m_eUnitType'].values())!=set(range(1,13))):
            raise ValueError('Ordinary99 chapter exact source identity')
    if row['npc_bindings']['10026']!=dict(houses=[40029],towns={'20010':778}):
        raise ValueError('Ordinary99 NPC10026 exact Elysion binding')
    for identity in (22352,22353):
        quest=row['quests'][str(identity)]
        if (quest['m_eQuestType']!=5 or quest['QuestCondition']['m_iLevel']!=99
            or set(quest['QuestCondition']['m_eUnitType'].values())!=set(range(1,13))):
            raise ValueError('Ordinary99 next dialogue exact source identity')
    for identity in (22355, 22357, 22359, 22360, 22361, 22363, 22365, 22367, 22369, 22370):
        quest=row['quests'][str(identity)]
        if (quest['m_eQuestType']!=5 or quest['QuestCondition']['m_iLevel']!=99
            or set(quest['QuestCondition']['m_eUnitType'].values())!=set(range(1,13))):
            raise ValueError('Ordinary99 chapter tail exact source identity')
    quest=row['quests']['28710']
    if (quest['QuestCondition']['m_eUnitType']!={'1':15}
        or quest['QuestCondition']['m_iLevel']!=1
        or quest['QuestCondition']['m_vecBeforeQuestID']!={'0':None,'1':28700}
        or quest['m_vecSubQuest']!={'0':None,'1':27190}):
        raise ValueError('Lithia departure next original dialogue source')
    if row['npc_bindings']['10222']!=dict(houses=[40168],towns={'20010':778}):
        raise ValueError('Lithia Elrianode source NPC10222 house40168')
    for identity,parent in ((28720,28710),(28730,28720),(28740,28730)):
        quest=row['quests'][str(identity)]
        if (quest['QuestCondition']['m_eUnitType']!={'1':15}
            or quest['QuestCondition']['m_vecBeforeQuestID']!={'0':None,'1':parent}
            or quest['m_vecSubQuest']!={'0':None,'1':28720}):
            raise ValueError('Lithia Elrianode exact NPC10222 tasks')
    if row['npc_bindings']['10025']!=dict(houses=[40028],towns={'1009':851,'20010':778}):
        raise ValueError('Ordinary Varnimyr original source NPC10025 scenes')
    for identity in (22378,22390,22420):
        quest=row['quests'][str(identity)]
        if (quest['QuestCondition']['m_iLevel']!=99
            or set(quest['QuestCondition']['m_eUnitType'].values())!=set(range(1,13))
            or quest['m_vecSubQuest']!={'0':None,'1':162120}):
            raise ValueError('Ordinary Varnimyr exact NPC10025 dialogue rows')
    if row['npc_bindings']['10235']!=dict(houses=[40193],towns={'1009':851}):
        raise ValueError('Ordinary Varnimyr original source NPC10235 scenes')
    for identity in (22450,22460):
        quest=row['quests'][str(identity)]
        if (quest['QuestCondition']['m_iLevel']!=99
            or set(quest['QuestCondition']['m_eUnitType'].values())!=set(range(1,13))
            or quest['m_vecSubQuest']!={'0':None,'1':22540}):
            raise ValueError('Ordinary Varnimyr exact NPC10235 dialogue rows')
    for identity in (22480,22490,22510,22520,22540,22560,22570):
        quest=row['quests'][str(identity)]
        if (quest['QuestCondition']['m_iLevel']!=99
            or set(quest['QuestCondition']['m_eUnitType'].values())!=set(range(1,13))
            or quest['m_vecSubQuest']!={'0':None,'1':22540}):
            raise ValueError('Original ordinary NPC10235 final seven dialogue rows')
    # Exact current Aurora camp and original mainline26680 reward successor.
    quest=row['quests']['23690']
    if (quest['m_eQuestType']!=5 or quest['QuestCondition']['m_iLevel']!=99
        or set(quest['QuestCondition']['m_eUnitType'].values())!=set(range(1,15))
        or quest['m_vecSubQuest']!={'0':None,'1':23550}
        or row['subquests']['23550']!=dict(m_iID=23550,m_eClearType=1,m_bAutomaticDescription=0,m_ClearCondition=dict(m_eTalkNPCID=10360))
        or row['npc_bindings']['10360']!=dict(houses=[40257],towns={'1010':964})):
        raise ValueError('Aurora original NPC10360 continuation identity')
    successor=row['quests']['23700']
    if (successor['m_eQuestType']!=5 or successor['QuestCondition']!=quest['QuestCondition']
        or successor['m_vecSubQuest']!={'0':None,'1':23550}
        or successor['m_iAfterQuestID']!={'0':None,'1':23710}):
        raise ValueError('Aurora original second NPC10360 dialogue')
    # Exact new NPC houses/scenes from this release's pinned source contract.
    for npc,binding in {'10229': {'houses': [40175], 'towns': {'20010': 778}}, '10381': {'houses': [40271], 'towns': {'20013': 1023}}, '10424': {'houses': [40310], 'towns': {'1011': 1131}}}.items():
        if row['npc_bindings'][npc]!=binding:raise ValueError('Mainline31 exact NPC source binding')
    if row['npc_bindings']['10500']!=dict(houses=[40326],towns={'1012':1214}):
        raise ValueError('Current original NPC10500 House40326 scene1214 identity')
    # Original26750 only: dialogue reward delivery, no housing activation.
    if (hashlib.sha256(json.dumps(row['quests']['26750'],sort_keys=True,separators=(',',':')).encode()).hexdigest()!='9b53b4309d98b85f892ef60773e3af07b3f9708281b224648f54d16dcbf7b703'
        or row['subquests']['26750']!={'m_iID':26750,'m_eClearType':1,'m_bAutomaticDescription':0,'m_ClearCondition':{'m_eTalkNPCID':10018}}):
        raise ValueError('Original26750 exact quest and objective source')
    # Exact account26780 contract delivery; housing activation is separate.
    if (hashlib.sha256(json.dumps(row['quests']['26780'],sort_keys=True,separators=(',',':')).encode()).hexdigest()!='d07de4b28505b179b94b410a16f6ae905495afb0418ad95c07b67c0e9ec516d0'
        or row['quests']['26780']['m_bIsAccount']!=1):raise ValueError('Original26780 exact account source')
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
