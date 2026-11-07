"""Compare writer projections with normal owned cold reads for saved LuCiel states."""
from pathlib import Path
import asyncio,importlib.util,json,sqlite3,sys
from contextlib import closing
H=Path(__file__).resolve().parent
sys.argv=[__file__,'--candidate',str(H/'candidate')]
spec=importlib.util.spec_from_file_location('owned_luciel_setup',H/'test_luciel.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
from els_server.storage.luciel_state import ensure,ensure_active
from els_server.storage.seal_quests import load_character
from els_server.storage.characters import Characters
from els_server.domain.character_stats import combat_values

async def run():
    f=t.r.f.FriendsTests();await f.asyncSetUp()
    try:
        chars=Characters(f.config.state_file,f.alice['id'])
        uid=chars.create('LuCielSql',10,'owned-projection')['uid']
        with closing(sqlite3.connect(f.config.state_file))as db,db:
            db.execute('BEGIN IMMEDIATE');ensure(db);ensure_active(db)
            item=t.grant_items(db,[dict(template=92112,metadata=0,group=2,quantity=1)],uid)[0]
            db.execute('UPDATE inventory_items SET bag_group=9,slot=17 WHERE uid=?',(item['uid'],))
        from els_server.storage.inventory_state import load_items
        cases=[]
        for style in range(3):
            for active in range(2):
                with closing(sqlite3.connect(f.config.state_file))as db,db:
                    db.execute('INSERT OR REPLACE INTO luciel_style_states VALUES (?,?,0)',(uid,style))
                    db.execute('INSERT OR REPLACE INTO luciel_active_states VALUES (?,?,0)',(uid,active))
                cold=chars.get(uid)
                with closing(sqlite3.connect(f.config.state_file))as db:
                    full=load_character(db,uid,f.alice['id']);identity=load_character(db,uid,f.alice['id'],identity_only=True)
                    items=load_items(db,uid)
                    assert (full['luciel_style'],full['luciel_active_unit'])==(style,active)
                    assert combat_values(full,items)==combat_values(cold,items)
                    assert 'luciel_style'not in identity and'luciel_active_unit'not in identity
                    try:combat_values(identity,items)
                    except ValueError as e:assert str(e)=='Missing authoritative LuCiel state'
                    else:raise AssertionError('The authoritative state guard was lost')
                cases.append(dict(style=style,active=active))
        return dict(ok=True,owned_SQLite=True,states=cases,saved_values_preserved=True,
            combat_profiles_match_normal_cold_read=True,identity_projection_unchanged=True,
            missing_authority_still_rejected=True,production_modified=False)
    finally:await f.asyncTearDown()

if __name__=='__main__':
    result=asyncio.run(run());(H/'projection-fixed.json').write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
