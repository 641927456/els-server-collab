"""Only current-client AccountQuest53520 and its one712413 reward source.

No page opening/use rules, fees, points, UI, effects or timers are inferred.
The item proof is a static record plus the reviewed generic304 codec and a
private roundtrip; it is explicitly not a native-execution success receipt.
"""
import functools,hashlib,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    p=PROJECT_ROOT/'els_server/data/erp_support_quest.json';raw=p.read_bytes()
    row=json.loads(raw);m=json.loads(p.with_suffix('.manifest.json').read_bytes())
    if (row['schema_version']!=1 or m['schema_version']!=1
        or row['client_sha256']!=CLIENT_SHA or m['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(raw).hexdigest()!=m['payload_sha256']
        or set(row['quests'])!={'53520'} or set(row['subquests'])!={'53520'}
        or type(row['source_mutations_enabled'])is not bool):
        raise ValueError('ERP support source identity')
    q=row['quests']['53520'];s=row['subquests']['53520'];c=q['QuestCondition']
    if (q['m_iID']!=53520 or q['m_eQuestType']!=5 or q['m_bIsAccount']!=1 or q['m_bRepeat']!=0 or q['m_bIsTimeEvent']!=0
        or c['m_iLevel']!=99 or c['m_iResonanceLevel']!=100 or s['m_iID']!=53520
        or c['m_vecBeforeQuestID']!={} or q.get('m_iAfterQuestID',0) or q.get('m_vecAfterQuestID',{})
        or s['m_eClearType']!=32 or s['m_ClearCondition']['m_iDungeonClearCount']!=100
        or q['Reward']['m_vecItem']!={'1':dict(m_iItemID=712413,m_sSocketOption=0,m_iPeriod=0,m_iQuantity=1)}
        or any(q['Reward'].get(k,0) for k in ('m_iSP','m_iBuff','m_iEP','m_iED','m_iEXP'))):
        raise ValueError('ERP support source scope')
    item=row['reward_definition'];native=client_data().item(712413)
    if (item['template'],item['metadata'],item['group'],item['max_stack'],item['finite_source_quantity'])!=(712413,0,4,1,1):
        raise ValueError('ERP support finite item definition')
    if (item['proof_kind']!='same-client-static-record-reviewed304-layout-private-roundtrip'
        or item['native_execution_claimed']is not False
        or hashlib.sha256(native['record']).hexdigest()!=item['record_sha256']
        or item['record_sha256']!='9da990fe2e9e8a83d89bfa48ce07054f586f0bfff5388374731d7675d81e264f'
        or native['item_type']!=7 or native['metadata']!=0
        or struct.unpack_from('<II',native['record'],4)!=(4198410,56)):
        raise ValueError('ERP support layered item evidence')
    return row

def item_definition():return catalog()['reward_definition']
