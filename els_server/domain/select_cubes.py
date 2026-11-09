"""Original selection lists, with unambiguous native item identities."""
import functools,hashlib,json,struct
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/select_cubes.json').read_bytes();data=json.loads(raw)
    manifest=json.loads((PROJECT_ROOT/'els_server/data/select_cubes.manifest.json').read_text())
    witness=(PROJECT_ROOT/manifest['proof']).read_bytes();native=json.loads(witness)
    if (data['client_sha256']!=CLIENT_SHA or hashlib.sha256(witness).hexdigest()!=manifest['proof_sha256']
        or native['catalog_sha256']!=hashlib.sha256(raw).hexdigest() or native['all_passed'] is not True
        or native['live_process_access'] is not False):raise ValueError('Selection cube native evidence')
    rows={r['template']:r for r in native['rows']};result={}
    if len(rows)!=len(data['definitions']):raise ValueError('Selection cube coverage')
    with client_data().connect() as db:
        for row in data['definitions']:
            t=row['template'];item=client_data().item(t);p=rows[t];rule=row['random_rule']
            if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or p['record_sha256']!=row['record_sha256']
                or row['metadata']!=item['metadata'] or row['name']!=item['name'] or row['group']!=4 or p['native_group']!=4
                or row['max_stack']!=row.get('source_max_stack',99) or row['selection_count']!=1
                or ('source_max_stack'in row and (type(row['source_max_stack'])is not int or row['source_max_stack']!=struct.unpack_from('<I',item['record'],0x10)[0]))
                or [(c['count'],c['ok'],c['consumed'],c['template'],c['metadata']) for c in p['cases']]
                    !=[(n,1,304,t,item['metadata']) for n in (1,99)]):raise ValueError('Selection cube item definition')
            if (rule['m_ItemID'],rule['m_iGiveCount'],rule['m_UseCondition'],rule['m_KeyItemID'],rule['m_RequiredKeyCount'])!=(t,1,1,0,0):
                raise ValueError('Selection cube use mode')
            entries=row['entries']
            if not 2<=len(entries)<=6 or len({e['template'] for e in entries})!=len(entries):raise ValueError('Selection cube choice bound')
            if t==723602 and tuple((e['template'],e['quantity']) for e in entries)!=((710313,50),(710315,50),(710314,50)):raise ValueError('Apple box original choices')
            if t==723603 and(tuple((e['template'],e['quantity'])for e in entries)!=((710206,5),(710207,5),(710210,5)) or hashlib.sha256(raw).hexdigest()!='03d8b2d2a22a46ab1dfe2b3b5e128433e24f63ef24d6d8ac59d650d31de85077' or manifest['proof_sha256']!='96362633694fbff9101ea02e55a320a84e9b3e60965521c71473cc84fad588cf'):raise ValueError('Elixir box source-owned contract')
            for e in entries:
                if 'record_sha256'in e:
                    source_item=client_data().item(e['template'])
                    proof_row=next((v for v in native.get('reward_rows',[])if v['template']==e['template']),None)
                    if (proof_row is None or proof_row['record_sha256']!=e['record_sha256'] or proof_row['native_group']!=e['group']
                        or e['group']!=4 or e['metadata']!=source_item['metadata'] or hashlib.sha256(source_item['record']).hexdigest()!=e['record_sha256']
                        or e['max_stack']!=struct.unpack_from('<I',source_item['record'],0x10)[0]):raise ValueError('Selection reward source identity')
                if not 1<=e['quantity']<=(50 if t==723602 else 10) or db.execute('SELECT id FROM items WHERE name=?',(e['name'],)).fetchall()!=[(e['template'],)]:
                    raise ValueError('Selection cube output identity')
            text='\n'.join('-'+e['name']+(str(e['quantity'])+'个' if e['quantity']!=1 else '') for e in entries)
            if row['description'].split('内含：\n',1)[1]not in(text,text+'\n中其中一个'):raise ValueError('Selection cube original contents')
            result[t]=MappingProxyType(row)
    return MappingProxyType(result)
