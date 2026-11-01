"""Pin all native ice equipment previews, including retired burner variants."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.shop_listing import ordinary_cash_equipment
BASE=ROOT/'analysis/client-6c6b5180'
SOURCES=('20261014-173316/IceHeaterPreView_INT.tables.json',
         '20261014-062215/ice-resources/IceHeaterPreView.tables.json')

def build():
    ids=set();pairs=set();data=client_data()
    for name in SOURCES:
        for call in json.loads((BASE/name).read_text(encoding='utf8'))['__symbolic_calls__']:
            if call['function'].endswith('.AddIceHeaterItemData'):
                _,machine,reward,role,*_=call['arguments'];ids.add(reward)
                if isinstance(role,dict):role=role['global'].split('.')[-1]
                pairs.add((machine,str(role),reward))
    with data.connect() as db:
        equipment={t for t, flags4 in db.execute('SELECT id,flags4 FROM items WHERE item_type IN (1,2,3)') if not ordinary_cash_equipment(flags4)}
    # Ordinary burner accessories are not seasonal preview rows. The official
    # guide names these families; pin their exact native templates as well.
    with data.connect() as db:
        common={t for t, in db.execute("SELECT id FROM items WHERE item_type=3 AND (name LIKE '奥利哈钢%' OR name LIKE '黄金闪耀围巾%' OR name LIKE '神圣护符%')")}
    out=dict(client_sha256=CLIENT_SHA,sources=[dict(path=n,sha256=hashlib.sha256((BASE/n).read_bytes()).hexdigest()) for n in SOURCES],
             templates=sorted(ids&equipment|common),seasonal_templates=sorted(ids&equipment),common_accessories=sorted(common),
             official_common_source='https://els.ztgame.com/game/000-1737-003de-127952.shtml?ms=990')
    path=ROOT/'analysis/shop-standalone-20261015/ice-shop-exclusions.json'
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(excluded=len(out['templates']),seasonal=len(out['seasonal_templates']),common=len(common))))

if __name__=='__main__':build()
