from pathlib import Path
import json,hashlib
ROOT=Path('G:/els');R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
exchange=ROOT/'analysis/equipment-connect-01a142e9/expansion-v2/ItemExchangeTable.lua.tables.json'
house=ROOT/'analysis/tutorial-quests-01a142ce/v3-remaining/resources/DLG_Map_House.lua.tables.json'
villages=ROOT/'analysis/x2-village-opcode14-20261017-01a14a51/outputs/DLG_Map_Village.tables.json'
call,=[c for c in json.loads(exchange.read_bytes())['__symbolic_calls__']if c['function']=='g_pItemManager.AddItemExchangeData'and c['arguments'][3]==714109]
assert call['arguments'][1:]==[40016,1,714109,714108,1,100,dict(m_iServerGroupID=-1,m_iSourceQuantity=20)]
h=json.loads(house.read_bytes())['House']['40016'];v=json.loads(villages.read_bytes())['Village']
assert h['NPC_ID_LIST']=={'1':10017}and h['NPCMeshName']=='Motion_Npc_All_Camilla.x'
data=dict(schema_version=1,house=40016,source=714109,source_quantity=20,destination=714108,quantity=1,rate=100,
    exchange_type=1,original_call=call,npc=10017,
    towns=sorted(int(k)for k,row in v.items()if 40016 in row.get('HouseIDList',{}).values()),
    source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in(exchange,house,villages)},
    official='https://els.ztgame.com/game/m_000-1656-0035d-384170.shtml?ms=859&mt=861')
target=R/'els_server/data/mount_racing_exchange.json';target.write_text(json.dumps(data,indent=2)+'\n',encoding='utf8')
print(dict(towns=data['towns'],sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
