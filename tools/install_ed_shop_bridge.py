"""Install the guarded local ED bridge through the current early owner only."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/pylibs')]
import psutil
RVAS=(0x69ca00,0x47bb40,0x47a770,0x23d6a80,0x31133f0,0x311c030,0x313a340,0x313a890,0x1c45370,0x1c4d500,0x1c71230,0x1c4e7a0)
def bridge_source(image,already_loaded=False):
    assert hashlib.sha256(image).hexdigest()=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
    from shop_state import quantity_catalog as catalog,home_lists
    from shop_messages import ed_catalog_ack
    from els_server.domain.character_rules import CLASSES
    from els_server.storage.characters import BASE_CLASSES
    by_base={v:k for k,v in BASE_CLASSES.items()}
    role_data={n:dict(size=len(ed_catalog_ack(catalog(n)).payload),home=home_lists(n)) for n in range(1,16)}
    bridge=(ROOT/'tools/local_ed_shop_bridge.js').read_text(encoding='utf8').replace('__ED_BRIDGE_PREFIXES__',json.dumps({r:image[r:r+8].hex() for r in RVAS})).replace('__ED_ALREADY_LOADED__','true' if already_loaded else 'false').replace('__ED_ROLE_DATA__',json.dumps(role_data)).replace('__ED_CLASS_TYPES__',json.dumps({k:by_base[v['base_class']] for k,v in CLASSES.items()}))
    preview=(ROOT/'tools/local_shop_preview_groups.js').read_text(encoding='utf8').replace('__PREVIEW_GROUP_PREFIXES__',json.dumps({r:image[r:r+16].hex() for r in (0x6a5e11,0x6a5e5f)}))
    quantities=(ROOT/'tools/local_ed_shop_quantities.js').read_text(encoding='utf8').replace('__SHOP_QUANTITY_PREFIXES__',json.dumps({r:image[r:r+16].hex() for r in (0x1c90010,0x1c90060,0x1c85fa0,0x1c87a50)}))
    return bridge+'\n'+preview+'\n'+quantities
if __name__=='__main__':
    run=Path(sys.argv[1]);i=json.loads((run/'client-process.json').read_text(encoding='utf8'));p=psutil.Process(i['pid'])
    assert i['shop_test'] and i['item_test'] and i['no_os_input'] and i['play'] is False
    assert not i.get('local_ed_shop_bridge'), 'The startup bridge already owns these hooks; use install_shop_open.py'
    assert abs(p.create_time()-i['created'])<.001 and Path(p.exe()).resolve()==Path(i['exe']).resolve()
    assert hashlib.sha256(Path(i['exe']).read_bytes()).hexdigest()==i['file_sha256']=='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
    image=(ROOT/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
    events=list(map(json.loads,(run/'server-console.jsonl').read_text(encoding='utf8').splitlines()))
    code=bridge_source(image,any(e.get('event')=='local_business_response_sent' and e.get('kind')==0x80e for e in events))
    if '--open' in sys.argv[2:] or '--close' in sys.argv[2:]:
        action=(ROOT/'tools/request_owned_shop.js').read_text(encoding='utf8').replace('__PREFIXES__',json.dumps({0x311c030:image[0x311c030:0x311c038].hex()})).replace('__CATALOG_PROBE__','false').replace('__AVAILABILITY_PROBE__','false')
        if '--close' in sys.argv[2:]:
            action=action.replace('!==0','!==1').replace('Shop is already open; refusing toggle','Shop is not open; refusing toggle').replace('native_shop_open_','native_shop_close_')
        code+='\n'+action
    (run/'probe-extension.js').write_text(code,encoding='utf8')
    print('Local ED bridge installed in the existing early owner.')
