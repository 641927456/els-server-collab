from pathlib import Path
import hashlib,json
W=Path(__file__).resolve().parent
source=Path('G:/els/analysis/client-6c6b5180/20261014-062215/ice-resources/RandomItem.all-tables.json')
raw=source.read_bytes();calls=json.loads(raw)['__symbolic_calls__']
rows={str(c['arguments'][1]['m_ItemID']):c['arguments'][1]for c in calls
      if c['function']=='g_pRandomItemManager.AddRandomItemTemplet'
      and c['arguments'][1].get('m_ItemID')in(132812,132840,90000746)}
assert set(rows)=={'132812','132840','90000746'}
data=dict(native_random_rules=rows,source_sha256=hashlib.sha256(raw).hexdigest(),
    source_path=str(source),stone_box=132812,
    pool=[dict(template=t,quantity=1,weight=2000)for t in(132198,132202,132203,132204,132205)],
    probability_authorization_sha256=hashlib.sha256((W/'stone-box-policy-authorization.json').read_bytes()).hexdigest())
p=W/'candidate/els_server/data/mentor_boxes.json';p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
print(hashlib.sha256(p.read_bytes()).hexdigest())
