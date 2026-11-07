"""Only four exact original account epic definitions; reward delivery only."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA
@functools.lru_cache(maxsize=1)
def catalog():
    p=PROJECT_ROOT/'els_server/data/account_epic_quests.json';raw=p.read_bytes()
    row=json.loads(raw);manifest=json.loads(p.with_suffix('.manifest.json').read_bytes())
    if (hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256'] or row['schema_version']!=1
        or row['client_sha256']!=CLIENT_SHA or set(row['quests'])!={'37100','53500','53510','53530'}
        or set(row['subquests'])!={'37100','53500','53510'}
        or manifest['quests']!=4 or manifest['subquests']!=3
        or set(row['source_mutations_enabled'])!={37100,53500,53510,53530}
        or set(row['reward_readers'])!={'712417','710105'} or manifest['reward_readers']!=2):raise ValueError('Finite account Epic catalog identity')
    expected={37100:(0,7,37100),53500:(10,5,53500),53510:(50,10,53510),53530:(150,10,53510)}
    for identity,(erp,count,sid) in expected.items():
        q=row['quests'][str(identity)];sub=row['subquests'][str(sid)];condition=q['QuestCondition']
        if (q['m_iID']!=identity or q['m_eQuestType']!=5 or q['m_bIsAccount']!=1 or q['m_bRepeat'] or q['m_bIsTimeEvent']
            or condition['m_iLevel']!=99 or condition.get('m_iResonanceLevel',0)!=erp
            or condition['m_vecBeforeQuestID']!={} or sub['m_eClearType']!=32
            or sub['m_ClearCondition']['m_iDungeonClearCount']!=count):raise ValueError('Original account Epic source scope')
    return row

def reward_item_definitions():
    """Only original unused reward instances; activation effects are separate."""
    import struct
    from els_server.game_data import client_data
    data=catalog();client=client_data();result=[]
    expected={712417:(0,4,1,0),710105:(2,4,300,300)}
    for template,(metadata,group,cap,word) in expected.items():
        row=data['reward_readers'][str(template)];item=client.item(template)
        if (row['template'],row['metadata'],row['group'],row['max_stack'],row['native_stack_word'])!=(template,metadata,group,cap,word):raise ValueError('Finite account Epic reward reader')
        if (item['item_type'],item['metadata'],struct.unpack_from('<I',item['record'],0x10)[0])!=(7,metadata,word) or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:raise ValueError('Original account Epic reward item source')
        result.append(row)
    return tuple(result)
