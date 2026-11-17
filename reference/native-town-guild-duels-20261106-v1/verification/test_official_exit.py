"""Exercise newly restored6A against actual official admission and writer."""
from pathlib import Path
import ast
source=Path(__file__).with_name('test_official_regression.py').read_bytes().decode('utf8')
def once(a,b):
    global source
    assert source.count(a)==1,(a,source.count(a));source=source.replace(a,b)
start=source.index('            await action(peers[0],0xa7,')
end=source.index('            profiles=',start)
source=source[:start]+'''            starts=[len(p.received)for p in peers]
            await action(peers[0],0x6a,reply=0x6b)
            notice=await observed(peers[0],0x6c,starts[0])
            assert struct.unpack_from('>bQI',notice.payload)==(5,values[0]['uid'],2)
            for p,start in zip(peers,starts):await observed(p,0xc2,start)
            assert sessions[0].phase=='map_loading'and pvp.room(sessions[0])is None
            assert sessions[1].phase=='pvp_result'and room.phase=='result'
            await action(peers[1],0x6a,reply=0x6b)
            await observed(peers[1],0x6c,starts[1])
'''+source[end:]
once("assert [p['ap']for p in profiles]==[10,40],profiles","assert [p['ap']for p in profiles]==[0,0],profiles")
once("assert [p['completed']for p in profiles]==[1,1]","assert [p['completed']for p in profiles]==[0,0]")
once("assert all(row[0]>0 for row in read('SELECT experience FROM reward_balances ORDER BY uid'))","assert all(row[0]==0 for row in read('SELECT experience FROM reward_balances ORDER BY uid'))")
once("official sealed result retains approved AP10/40 and positive XP; only official ledger changes","official6A before30s retains existing leave/aborted policy, zero initial AP/XP/completions and one official receipt; challenge ledger stays empty")
start=source.index('            # Persist a manual challenge refusal,')
end=source.index("            report['ok']=True",start)
source=source[:start]+source[end:]
source=source.replace('owned-official-regression-','owned-official-exit-').replace("'official-regression-'","'official-exit-'")
ast.parse(source)
exec(compile(source,str(Path(__file__).resolve()),'exec'),{'__name__':'__main__','__file__':__file__})
