"""Validate exact archived source bytes and an optional independently accepted parent."""
import argparse,ast,hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];ART=ROOT/'references/native-change-force-materials-20261027-v1'
MANIFEST_SHA='c977e1f05649f8025eeb86a5a22fa93a83d4fa873e9f093a1d3065617dcbe953'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def probe(root,parent=None):
    root=Path(root);inventory=root/'els_server/storage/boosting_2026_force_inventory.py';equipment=root/'els_server/storage/boosting_2026_force_equipment.py'
    tree=ast.parse(inventory.read_text('utf8'));function=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='initialize_change')
    scope={};exec(compile(ast.Module(body=[function],type_ignores=[]),str(inventory),'exec'),scope)
    ddl=[node.value for node in ast.walk(ast.parse(equipment.read_text('utf8')))if isinstance(node,ast.Constant)and isinstance(node.value,str)and 'CREATE TABLE IF NOT EXISTS selected_2026_change_force_slots ('in node.value]
    assert len(ddl)==1
    names={'selected_2026_change_force_inventory','selected_2026_change_force_slots'}
    mentions=[]
    if parent is not None:
        for p in (Path(parent)/'els_server').rglob('*.py'):
            if any(n in p.read_text('utf8')for n in names):mentions.append(str(p))
        assert not mentions,'These definitions already occur in the selected parent'
    with sqlite3.connect(':memory:')as db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY)');db.execute('INSERT INTO characters VALUES(1001)');db.commit()
        before=db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name').fetchall()
        db.execute('SAVEPOINT mod360_schema_review')
        scope['initialize_change'](db);db.execute(ddl[0])
        assert {r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}-{'characters'}==names
        info={n:db.execute('PRAGMA table_info('+n+')').fetchall()for n in names}
        pks={n:[r[1]for r in sorted(info[n],key=lambda r:r[5])if r[5]]for n in names}
        assert pks['selected_2026_change_force_inventory']==['owner','skill','rank']and pks['selected_2026_change_force_slots']==['owner','slot']
        fks={n:db.execute('PRAGMA foreign_key_list('+n+')').fetchall()for n in names}
        assert [(r[2],r[3],r[4])for r in fks['selected_2026_change_force_inventory']]==[('characters','owner','uid')]
        assert {(r[2],r[3],r[4])for r in fks['selected_2026_change_force_slots']}=={('selected_2026_change_force_inventory',c,c)for c in('owner','skill','rank')}
        db.execute('INSERT INTO selected_2026_change_force_inventory VALUES(1001,901012,1,300550,0)');db.execute('INSERT INTO selected_2026_change_force_slots VALUES(1001,0,901012,1)')
        negatives=[('owner-FK','INSERT INTO selected_2026_change_force_inventory VALUES(1002,901013,1,300551,0)'),('rank-CHECK','INSERT INTO selected_2026_change_force_inventory VALUES(1001,901013,2,300551,0)'),('source-UNIQUE','INSERT INTO selected_2026_change_force_inventory VALUES(1001,901013,1,300550,0)'),('slot-CHECK','INSERT INTO selected_2026_change_force_slots VALUES(1001,8,901012,1)'),('slot-FK','INSERT INTO selected_2026_change_force_slots VALUES(1001,1,901013,1)'),('slot-PK','INSERT INTO selected_2026_change_force_slots VALUES(1001,0,901012,1)')]
        rejected=[]
        for label,sql in negatives:
            try:db.execute(sql)
            except sqlite3.IntegrityError:rejected.append(label)
            else:raise AssertionError(label+' was accepted')
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        db.execute('ROLLBACK TO mod360_schema_review');db.execute('RELEASE mod360_schema_review')
        assert db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name').fetchall()==before
    return dict(ok=True,private_SQLite_memory_only=True,exact_initialize_change_function_executed=True,exact_slots_DDL_executed=True,new_lazy_tables=2,new_schema_definitions=2,install_DDL_statements=0,parent_source_definitions_absent=not mentions if parent is not None else None,actual_parent_player_database_inspected=False,PK=pks,FK=fks,negative_constraints_rejected=rejected,savepoint_rollback_removed_both_tables=True,source_SHA256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in(inventory,equipment)})

def main():
 p=argparse.ArgumentParser();p.add_argument('--channel',choices=('online','local'),default='online');p.add_argument('--parent',type=Path);p.add_argument('--full-parent',action='store_true');a=p.parse_args()
 assert sha(ART/'manifest.json')==MANIFEST_SHA;m=json.loads((ART/'manifest.json').read_bytes());c=m['channels'][a.channel];rows=c['runtime_leaves']
 assert len(rows)==16 and len({r['path']for r in rows})==16 and sum(r['new_file']for r in rows)==3
 assert m['new_tables']==2 and m['new_schema_definitions']==2 and m['new_schema']is True and m['install_DDL']==0
 for row in rows:
  path=ART/row['archive_path'];assert sha(path)==row['sha256']and path.stat().st_size==row['size'];assert row['new_file']==(row['parent_sha256']is None)
  if path.suffix=='.py':ast.parse(path.read_text('utf-8-sig'))
  elif path.suffix=='.json':json.loads(path.read_bytes())
 if a.parent:
  mf=a.parent/c['parent_manifest_name'];assert sha(mf)==c['parent_manifest_sha256'];d=json.loads(mf.read_bytes());assert d['release']==c['parent_release'];parent={r['path']:r for r in d['files']}
  for row in rows:assert row['parent_sha256']==parent.get(row['path'],{}).get('sha256')
  if a.full_parent:
   for row in parent.values():assert sha(a.parent/row['path'])==row['sha256']
 schema=probe(ART/'shared',a.parent)
 print(json.dumps(dict(schema_probe=schema,ok=True,channel=a.channel,delta16=True,new_files3=True,new_lazy_tables2=True,installDDL0=True,schema_rollback=True,full_parent=a.full_parent)))
if __name__=='__main__':main()
