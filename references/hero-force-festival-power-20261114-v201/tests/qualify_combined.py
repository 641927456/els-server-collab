"""Bind existing successful tests and the corrected CP fixture to final inputs."""
import ctypes,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_final_scope import H,P,THREE,PREVIOUS,CP,ROOT,read,save,pin,sha
R=H/'runtime/combined';sys.path[:0]=[str(R),str(R/'tools')]
ctypes.WinDLL(str(R/'python/sqlite3.dll'))
import sqlite3
assert not sys._is_gil_enabled()and sqlite3.sqlite_version=='3.54.1'
import business_fixture as fixture
path=H/'checks/flow/game.sqlite3'
with sqlite3.connect((path.parent/'accounts.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)as registry:
    ids=[row[0]for row in registry.execute("SELECT id FROM accounts WHERE name LIKE 'qa200flow%' ORDER BY id")]
with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)as db:
    assert len(ids)==4
    rows=[]
    for index,account in enumerate(ids[:3]):
        uid,=db.execute('SELECT uid FROM character_owners WHERE account_id=?',(account,)).fetchone()
        rows.append(dict(account_id=account,uid=uid,index=index,scenario='hero_force'if index<2 else'festival'))
cold=fixture.cold(rows,path,retired=False)
assert cold['ok'] and len(cold['roles'])==3
save(H/'checks/flow/final-three-cold.json',cold)
power=read(H/'checks/power-wire-v2/result.json');assert power['ok']
bindings={row['path']:row['sha256']for row in read(H/'composition.json')['files']if row['scope']=='server'}
assert power['source_bindings']==bindings
old=read(PREVIOUS/'checks/flow/result.json');assert old['ok']
sources={
 'three_feature_two_phase_TLS':pin(PREVIOUS/'checks/flow/result.json'),
 'final_three_read_only_cold':pin(H/'checks/flow/final-three-cold.json'),
 'final_power_two_phase_TLS':pin(H/'checks/power-wire-v2/result.json'),
 'v200_inventory_read_equivalence':pin(P/'source-acceptance.json'),
 'final_CP_business':pin(CP/'checks/business-verification.json')}
explanation='The first final-runtime test phase completed all four cases. Its cold CP assertion exposed a fixture ERP threshold changed from 200 to 201 during version adaptation. Preserve that failed attempt; run the corrected CP case alone through both phases. Reuse the unchanged Hero/Force/festival two-phase TLS success, add final-runtime read-only cold evidence, and require all four cases again in the actual public delivery transaction.'
save(H/'checks/flow/result.json',dict(ok=True,actual_TLS=True,public_network=False,native_session=False,source_bindings=bindings,evidence=sources,one_four_account_two_phase_run=False,fixture_failure_and_resolution=explanation,owned_cleanup=pin(H/'checks/flow/cleanup.json')))
checks={row['path']:pin(CP/row['path'])for row in read(CP/'manifest.json')['checks']}
assert all(read(ref['path']).get('ok',True)for ref in checks.values())
save(H/'checks/result.json',dict(ok=True,scope='17 final server leaves; signed native activation is qualified separately',source_bindings=bindings,unchanged_three_repair_tests=pin(THREE/'checks/result.json'),actual_combined_TLS=pin(H/'checks/flow/result.json'),accepted_CP_checks=checks,launcher_start=pin(H/'launcher-start-acceptance.json'),natural_GUI=False,natural_battle=False))
print('Bound final server qualification; preserved fixture failure and reused unchanged cases')
