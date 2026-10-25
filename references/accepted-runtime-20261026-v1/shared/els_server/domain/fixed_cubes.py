"""Fixed contents backed by original KIM descriptions and native cube rules."""
import functools,hashlib,json,re
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/fixed_cubes.json').read_bytes();data=json.loads(raw)
    manifest=json.loads((PROJECT_ROOT/'els_server/data/fixed_cubes.manifest.json').read_text())
    native_raw=(PROJECT_ROOT/manifest['proof']).read_bytes();proof=json.loads(native_raw)
    if (hashlib.sha256(native_raw).hexdigest()!=manifest['proof_sha256'] or proof['catalog_sha256']!=hashlib.sha256(raw).hexdigest()
        or data['client_sha256']!=CLIENT_SHA or data['source_catalog_sha256']!=client_data().manifest['catalog_sha256']
        or proof['live_process_access'] is not False or proof['all_passed'] is not True
        or proof['kim_record_coverage']!=data['kim_record_coverage'] or data['kim_record_coverage']!=181836):
        raise ValueError('Fixed cube native evidence identity')
    native={r['template']:r for r in proof['rows']};result={}
    if len(native)!=proof['count'] or len(native)!=len(data['definitions']):raise ValueError('Fixed cube evidence coverage')
    with client_data().connect() as db:
        for row in data['definitions']:
            t=row['template'];item=client_data().item(t);w=native[t];rule=row['random_rule']
            if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or w['record_sha256']!=row['record_sha256']
                or item['name']!=row['name'] or item['metadata']!=row['metadata'] or row['group']!=4 or w['native_group']!=4
                or row['max_stack']!=99 or len(w['cases'])!=2
                or [(c['count'],c['ok'],c['consumed'],c['native_template'],c['metadata']) for c in w['cases']]
                    !=[(n,1,304,t,row['metadata']) for n in (1,99)]):raise ValueError('Fixed cube native item definition')
            if (rule['m_ItemID']!=t or rule['m_iGiveCount']!=0 or rule['m_UseCondition']!=1
                or rule['m_KeyItemID']!=0 or rule['m_RequiredKeyCount']!=0):raise ValueError('Fixed cube use mode')
            match=re.fullmatch(r'内含([1-9][0-9]*)个(.+)的宝箱。',row['description'])
            if not match or (int(match[1]),match[2])!=(row['quantity'],row['reward_name']) or not 1<=row['quantity']<=1000:
                raise ValueError('Fixed cube original description')
            if db.execute('SELECT id FROM items WHERE name=?',(row['reward_name'],)).fetchall()!=[(row['reward'],)]:
                raise ValueError('Ambiguous fixed cube output identity')
            if t in result:raise ValueError('Duplicate fixed cube')
            result[t]=MappingProxyType(row)
    return MappingProxyType(result)
