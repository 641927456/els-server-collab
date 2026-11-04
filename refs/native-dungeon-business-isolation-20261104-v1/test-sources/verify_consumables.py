from pathlib import Path
p=Path('G:/els/analysis/pickup-consumable-gate-20261104-v1/verify_consumables.py')
source=p.read_text('utf8')
source=source.replace("    assert any(e.kind==0xba for e in periodic(s));assert s.dungeon_clock.started is None", """    assert any(e.kind==0xb7 for e in periodic(s))
    target=struct.pack('>b',r.next['part'])
    replies=s.handle(Event(0x202,kind=0xb8,performers=(0,),payload=target),900000)
    assert any(e.kind==0xba for e in replies);assert s.dungeon_clock.started is None""")
failed=Path(__file__).parent/'consumable-tests-candidate.json'
if failed.exists()and not __import__('json').loads(failed.read_bytes())['ok']:
 failed.rename(failed.with_name('consumable-fixture-before-glass-update-failure.json'))
exec(compile(source,str(p),'exec'))
