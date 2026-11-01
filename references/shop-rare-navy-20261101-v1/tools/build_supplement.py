"""Complete the audited local sets from native membership/preview/custom links."""
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

W=Path(__file__).resolve().parent
C=W/'candidate'
sys.dont_write_bytecode=True
sys.path.insert(0,str(C))
from els_server.game_data import client_data
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
from els_server.domain.acquisition_policy import has_legacy_marker

def read(p):return json.loads(p.read_bytes())
def save(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n','utf8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def walk(v):
    if isinstance(v,dict):
        if 'CUSTOM_ID'in v:yield v
        for x in v.values():yield from walk(x)
    elif isinstance(v,list):
        for x in v:yield from walk(x)
def numbers(v):
    if type(v)is int:yield v
    elif isinstance(v,dict):
        for x in v.values():yield from numbers(x)
    elif isinstance(v,list):
        for x in v:yield from numbers(x)

D=client_data()
with D.connect()as db:
    items={r[0]:dict(zip(('template','name','flags4','flags8','type','metadata','position','raw'),r))
        for r in db.execute('SELECT id,name,flags4,flags8,item_type,metadata,equip_position,record FROM items')}
a=read(W/'audit-online.json')
path=C/'analysis/shop-listing-20261015/fashion-bundles.json'
old=read(path)
existing={r['template']:r for r in old['offers']}
definitions={r['template']:r for r in old['definitions']}
ice=set(read(C/'analysis/shop-standalone-20261015/ice-shop-exclusions.json')['templates'])
custom_source='analysis/shop-missing-20261031-v1/CharCustomData.tables.json'
calls=read(C/custom_source)['__symbolic_calls__']
families={'MOTION':(1,1),'SIT_MOTION':(7,7),'SKILL_CUT':(3,3),'FACE':(2,2),'HYPER_EFFECT':(15,15)}
by_book={};by_custom={};gifts=collections.defaultdict(list)
for call in calls:
    kind=next((k for k in families if call['function'].endswith('.CHAR_CUSTOM_'+k+'_DATA')),None)
    if kind is None:continue
    for row in walk(call['arguments']):
        if 'ITEM_ID'not in row:continue
        row=dict(row,family=families[kind][0],slot=families[kind][1])
        by_custom[row['CUSTOM_ID']]=row
        if type(row['ITEM_ID'])is int and row['ITEM_ID']>0:by_book[row['ITEM_ID']]=row
        for t in numbers(row.get('PACKAGE_ITEM_ID',{})):
            if row['ITEM_ID'] not in gifts[t]:gifts[t].append(row['ITEM_ID'])
replacements={c['arguments'][1]:c['arguments'][2:]for c in calls if c['function'].endswith('AddReplaceCustomID')}
permanent_path=C/'els_server/data/character_custom_permanent.json'
custom=read(permanent_path)
books={r['book']:r for r in custom['books']}
customs={r['custom_id']:r for r in custom['customs']}
added_books=[]
def variant(row):return (2 if row.get('IS_MAJOR',0)else 3)if row['UNIT_TYPE']==10 else 1
def admit_book(t):
    if t in books:return
    row=by_book[t];item=items[t];raw=item['raw']
    assert item['type']==14 and row['UNIT_TYPE']==raw[210]and not row.get('ACCOUNT_CUSTOM',False),(t,'native book')
    cid=row['CUSTOM_ID'];ids=replacements.get(cid,[cid])
    assert all(i in by_custom for i in ids),(t,'replacement source')
    rule=dict(book=t,custom_id=cid,type=row['family'],slot=row['slot'],unit_type=raw[210],units=[raw[210]],
        native_item_sha256=hashlib.sha256(raw).hexdigest(),variant=variant(row),
        ability_group=row.get('ALLOW_SOCKET_OPTION_GROUP'),custom_ids=ids)
    custom['books'].append(rule);books[t]=rule;added_books.append(t)
    for i in ids:
        source=by_custom[i]
        cr=dict(custom_id=i,type=source['family'],variant=variant(source),ability_group=source.get('ALLOW_SOCKET_OPTION_GROUP'))
        if i in customs:assert customs[i]==cr,(t,i,'custom collision')
        else:custom['customs'].append(cr);customs[i]=cr

rows={r['template']:r for r in a['paired_missing']}
# Navy canonical parents have their own preview. Four obsolete same-name
# Lu/Ciel beach parents without preview are deliberately not duplicated.
for r in a['navy']:
    if not r['listed']and r['preview_members']and not r['same_name_listed']:
        if any(s in r['name']for s in('海军服特别','沙滩床','水手泳装')):rows[r['template']]=r
added=[];held=[];decisions=[]
for t,r in sorted(rows.items()):
    assert t not in existing
    bases=[existing[x]for x in r['ordinary_listed_matches']]
    normal_name=r['name'].replace('稀有','').replace('特别','').replace('沙滩床','')
    exact_bases=[b for b in bases if b['name']==normal_name]
    if exact_bases:bases=exact_bases
    base_ids={i for b in bases for i in b['contents']}
    role=r['role']
    if role==0 and bases:
        allowed={int(n)for b in bases for n in b['contents_by_role']}
        assert len(allowed)==1
        role=next(iter(allowed))
    assert role in range(1,16),(t,'role')
    versions=r['package_sources']
    selected=None;basis=None
    if versions:
        # Native full-set variant retains the already sold normal set. This
        # selects the INT seven-piece version when a regional six-piece row
        # replaces the normal hair with its alternate hat.
        candidates=[v for v in versions if all(p==0 and visible for _,p,visible in v['entries'])]
        matching=[v for v in candidates if base_ids<={i for i,_,_ in v['entries']}]
        if not matching:matching=candidates
        distinct={tuple(i for i,_,_ in v['entries'])for v in matching}
        if len(distinct)==1:
            selected=list(next(iter(distinct)));basis=dict(kind='native package',source=[v['source']for v in matching])
    if selected is None and r['preview_sources']:
        candidates=[v for v in r['preview_sources']if not base_ids or base_ids<=set(v['children'])]
        if not candidates:candidates=r['preview_sources']
        distinct={tuple(v['children'])for v in candidates}
        if len(distinct)==1:
            selected=list(next(iter(distinct)));basis=dict(kind='native preview complete-set local delivery',source=[v['source']for v in candidates])
    if selected is None and bases and role==10:
        # Existing combined Lu/Ciel normal products expand both side sets.
        # Compose their explicit rare previews only when the matching normal
        # side memberships exactly partition the combined normal membership.
        sides=[x for x in rows.values()if x['template']!=t and x['role']==10 and x['preview_members']
            and x['ordinary_listed_matches'] and x['family']==r['family']
            and {i for b in x['ordinary_listed_matches']for i in existing[b]['contents']}<base_ids]
        cover={i for x in sides for b in x['ordinary_listed_matches']for i in existing[b]['contents']}
        if cover==base_ids:
            selected=list(dict.fromkeys(i['template']for x in sides for i in x['preview_members']))
            basis=dict(kind='local combined Lu/Ciel from exact two side previews',source=[x['template']for x in sides])
    if selected is None:
        held.append(dict(template=t,name=r['name'],reason='No unambiguous native membership/preview; resource name alone is insufficient.'))
        continue
    extras=gifts[t]
    selected=list(dict.fromkeys([*selected,*extras]))
    assert 5<=len(selected)<=36,(t,len(selected))
    assert not set(selected)&ice,(t,'ice equipment')
    for i in selected:
        it=items[i]
        assert it['raw'][210]in(0,role),(t,i,'foreign role')
        assert not has_legacy_marker(it['name']) and not any(s in it['name']for s in('[科宝]','[路莉尔]','[阿莉尔]','[GM]','测试','体验')),(t,i,'excluded source')
        if it['type']==14:admit_book(i)
        else:
            assert it['type']in(1,2,3),(t,i,'member type')
            assert it['flags4']&1 or (i in VERIFIED_TEMPLATES and TEMPLATE_BAG_GROUPS[i]==2),(t,i,'equipment classification')
    assert {6,8,9,10,11}<={items[i]['position']for i in selected if items[i]['type']in(1,2,3)}
    product=dict(template=t,name=r['name'],unit_type=role,kind='costume',category=52,price=50,quantity=1,
        contents=selected,contents_by_role={str(role):selected})
    added.append(product)
    decisions.append(dict(template=t,name=r['name'],basis=basis,extra_custom_books=extras,contents=selected,
        ordinary_templates=r['ordinary_listed_matches']))
    for i in [t,*selected]:
        if i in definitions:continue
        it=items[i]
        group=(27 if it['flags8']&256 else 7)if it['flags4']&1 else TEMPLATE_BAG_GROUPS.get(i,4)
        definitions[i]=dict(template=i,name=it['name'],metadata=it['metadata'],group=group,
            max_stack=TEMPLATE_MAX_STACKS.get(i,1 if it['flags4']&1 or it['type']==14 else 99),
            resource_position_byte=it['position'],record_hex=it['raw'].hex())

assert len(held)==28 and all('幻龙降临'in x['name']for x in held),[(x['template'],x['name'])for x in held]
supplement_rel='analysis/shop-rare-navy-20261101-v1/bundle-membership.json'
supplement=dict(client_sha256=old['client_sha256'],source_date='2026-11-01',
    policy='Human requested rare/navy completion. Existing local permanent complete-set direct delivery at50ED; native package/preview costume members plus explicit PACKAGE_ITEM_ID linked custom books. No random rewards or inferred probabilities.',
    custom_source=custom_source,custom_source_sha256=digest(C/custom_source),decisions=decisions,held=held)
save(C/supplement_rel,supplement)
old['offers'].extend(added)
old['definitions']=[definitions[t]for t in sorted(definitions)]
old['costume_package_templates']=sorted(set(old['costume_package_templates'])|{r['template']for r in added})
old['sources'].append(dict(path=supplement_rel,sha256=digest(C/supplement_rel)))
old['sources'].append(dict(path=custom_source,sha256=digest(C/custom_source)))
old['policy']+='2026-11-01 native rare previews and PACKAGE_ITEM_ID-linked permanent custom books admitted for audited missing versions.'
save(path.with_name('fashion-bundles.candidate.json'),old)
custom['scope']+=';2026-11-01 audited rare/navy PACKAGE_ITEM_ID-linked permanent custom book sources.'
save(permanent_path,custom)
domain=C/'els_server/domain/character_custom.py';text=domain.read_text('utf8')
old_hash=re.search(r"hexdigest\(\)!='([a-f0-9]{64})'",text).group(1)
text=text.replace(old_hash,digest(permanent_path))
for name,rs in [('COUNTS',custom['customs']),('SOURCE_COUNTS',custom['books'])]:
    line=next(l for l in text.splitlines()if l.startswith(name+'='))
    keys=eval(line.split('=',1)[1],{'__builtins__':{}})
    text=text.replace(line,name+'='+repr({k:sum(x['type']==k for x in rs)for k in keys}))
domain.write_text(text,'utf8')
domain=C/'els_server/domain/fashion_bundles.py';text=domain.read_text('utf8')
for before,after in [("r['group'] not in (7, 27)","r['group'] not in (2, 4, 7, 27)"),
    ("not 2 <= len(ids) <= 12","not 2 <= len(ids) <= 36")]:
    assert text.count(before)==1,before
    text=text.replace(before,after)
domain.write_text(text,'utf8')
# Keep old definitions/proofs unmodified; a separate native verifier binds all
# new DTOs and group classifiers before promoting the candidate catalog.
save(W/'candidate-scope.json',dict(added_packages=added,added_books=added_books,held=held,
    input_candidates=len(rows),new_definition_count=len(definitions)-len(read(path)['definitions']),
    all_packages=len(old['offers']),custom_book_count=len(custom['books']),new_schema=False,price_ED=50))
print(json.dumps(dict(added_packages=len(added),added_books=len(added_books),held=len(held),new_definitions=len(definitions)-len(read(path)['definitions']),all_packages=len(old['offers'])),ensure_ascii=False))
