from pathlib import Path
ROOT=Path('G:/els');H=Path(__file__).resolve().parent
BASE=ROOT/'releases/online/native-first-pickup-prewarm-20261104-v1'
s=(ROOT/'analysis/pickup-consumable-gate-20261104-v1/runtime_fixture.py').read_text('utf8')
s=s.replace("BASE=ROOT/'releases/online/native-mixed-player-scene-summons-20261104-v1'",'BASE=Path('+repr(str(BASE))+')')
s=s.replace('import els_server.domain,els_server.storage',"import els_server,els_server.domain,els_server.storage\nif '--candidate'in sys.argv:els_server.__path__.insert(0,str(H/'candidate/els_server'))")
exec(compile(s,str(__file__),'exec'))
