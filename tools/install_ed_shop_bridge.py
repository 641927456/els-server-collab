"""Generate the retained native ED adapter from signed exact-catalogue support."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/pylibs')]
import psutil
RVAS=(0x69ca00,0x47bb40,0x47a770,0x23d6a80,0x31133f0,0x311c030,0x313a340,0x313a890,0x313abce,0x313ac83,0x1c45370,0x1c4d500,0x1c71230,0x1c4e7a0)
CATALOGUE_SUPPORT_SHA256='f945ff234f4de4378749bd08e491055edd29955646d5a050d8da0427aed6d9b4'

def catalogue_support():
    # This file is also a signed updater component. The fixed content digest
    # binds native resources/home candidates to this generator. Legal server
    # catalogue changes do not need a client update just to match a hash/length.
    raw=(ROOT/'tools/ed_shop_catalogs.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOGUE_SUPPORT_SHA256:
        raise ValueError('ED catalogue support identity; use normal launcher update')
    data=json.loads(raw)
    if data.get('schema_version')!=1 or set(data.get('roles',{}))!={str(n)for n in range(1,16)}:
        raise ValueError('ED catalogue support role coverage')
    return data

def role_profiles(data=None):
    data=catalogue_support()if data is None else data
    result={}
    for n in range(1,16):
        rows=data['roles'][str(n)]
        if not isinstance(rows,list)or not 1<=len(rows)<=2:raise ValueError('ED catalogue profile count')
        result[n]=[];seen=set()
        for row in rows:
            count=row.get('count');size=row.get('size');digest=row.get('sha256');home=row.get('home')
            if(type(count)is not int or not 0<count<=20000 or type(size)is not int or size!=5+28*count
                or not isinstance(digest,str)or len(digest)!=64 or any(c not in'0123456789abcdef'for c in digest)or digest in seen
                or not isinstance(home,list)or len(home)!=3
                or any(not isinstance(group,list)or len(group)>128 or len(set(group))!=len(group)
                       or any(type(t)is not int or not 0<t<2**31 for t in group)for group in home)):
                raise ValueError('ED catalogue profile shape')
            seen.add(digest);result[n].append(dict(count=count,size=size,sha256=digest,home=home))
    return result

def native_resources(data):
    native=data.get('native',{})
    if(native.get('client_sha256')!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
        or not isinstance(native.get('item_ranges'),list)or not isinstance(native.get('categories'),list)
        or not isinstance(native.get('role_masks'),dict)):
        raise ValueError('ED native resource identity')
    last=0;count=0
    for pair in native['item_ranges']:
        if not isinstance(pair,list)or len(pair)!=2 or any(type(v)is not int for v in pair)or not last<pair[0]<=pair[1]<2**31:
            raise ValueError('ED native item range')
        last=pair[1];count+=pair[1]-pair[0]+1
    if count!=native['item_count']or count>1000000:raise ValueError('ED native item coverage')
    if any(type(v)is not int or not 0<=v<2**31 for v in native['categories']):raise ValueError('ED native category identity')
    if any(not k.isdecimal()or not 0<int(k)<2**31 or type(v)is not int or not 0<v<(1<<15)for k,v in native['role_masks'].items()):raise ValueError('ED native role mask')
    return{key:native[key]for key in('item_ranges','categories','role_masks')}

def bridge_source(image,already_loaded=False):
    assert hashlib.sha256(image).hexdigest()=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
    from els_server.domain.character_rules import CLASSES
    from els_server.storage.characters import BASE_CLASSES
    by_base={v:k for k,v in BASE_CLASSES.items()}
    data=catalogue_support();role_data=role_profiles(data)
    bridge=(ROOT/'tools/local_ed_shop_bridge.js').read_text(encoding='utf8').replace('__ED_BRIDGE_PREFIXES__',json.dumps({r:image[r:r+(13 if r==0x313abce else 8)].hex()for r in RVAS})).replace('__ED_ALREADY_LOADED__','true'if already_loaded else'false').replace('__ED_ROLE_DATA__',json.dumps(role_data)).replace('__ED_NATIVE_DATA__',json.dumps(native_resources(data))).replace('__ED_CLASS_TYPES__',json.dumps({k:by_base[v['base_class']]for k,v in CLASSES.items()}))
    preview=(ROOT/'tools/local_shop_preview_groups.js').read_text(encoding='utf8').replace('__PREVIEW_GROUP_PREFIXES__',json.dumps({r:image[r:r+16].hex()for r in(0x6a5e11,0x6a5e5f)}))
    quantities=(ROOT/'tools/local_ed_shop_quantities.js').read_text(encoding='utf8').replace('__SHOP_QUANTITY_PREFIXES__',json.dumps({r:image[r:r+16].hex()for r in(0x1c90010,0x1c90060,0x1c85fa0,0x1c87a50)}))
    return bridge+'\n'+preview+'\n'+quantities

if __name__=='__main__':
    run=Path(sys.argv[1]);i=json.loads((run/'client-process.json').read_text(encoding='utf8'));p=psutil.Process(i['pid'])
    assert i['shop_test']and i['item_test']and i['no_os_input']and i['play']is False
    assert not i.get('local_ed_shop_bridge'),'The startup bridge already owns these hooks; use install_shop_open.py'
    assert abs(p.create_time()-i['created'])<.001 and Path(p.exe()).resolve()==Path(i['exe']).resolve()
    assert hashlib.sha256(Path(i['exe']).read_bytes()).hexdigest()==i['file_sha256']=='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
    image=(ROOT/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
    events=list(map(json.loads,(run/'server-console.jsonl').read_text(encoding='utf8').splitlines()))
    code=bridge_source(image,any(e.get('event')=='local_business_response_sent'and e.get('kind')==0x80e for e in events))
    if '--open'in sys.argv[2:]or'--close'in sys.argv[2:]:
        action=(ROOT/'tools/request_owned_shop.js').read_text(encoding='utf8').replace('__PREFIXES__',json.dumps({0x311c030:image[0x311c030:0x311c038].hex()})).replace('__CATALOG_PROBE__','false').replace('__AVAILABILITY_PROBE__','false')
        if '--close'in sys.argv[2:]:
            action=action.replace('!==0','!==1').replace('Shop is already open; refusing toggle','Shop is not open; refusing toggle').replace('native_shop_open_','native_shop_close_')
        code+='\n'+action
    (run/'probe-extension.js').write_text(code,encoding='utf8')
    print('Local ED bridge installed in the existing early owner.')
