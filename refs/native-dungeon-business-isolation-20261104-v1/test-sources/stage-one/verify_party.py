"""Reuse normal two-client admission/death/gate QA on the current overlay."""
import runtime_fixture as h
import sys
sys.modules['gate_probe']=h.load('gate_probe',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
source=(h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/precheck_party.py').read_text(encoding='utf8')
source=source.replace("            peer=await c.peer(account);", "            from els_server.storage.characters import Characters\n            Characters(c.config.state_file,account['id']).create('Player'+str(account['id']),10,'owned-party-'+str(account['id']))\n            peer=await c.peer(account);")
source=source.replace("        run=DungeonRun(34710,str(uuid.uuid4()));", """        # The same lightweight actor identity must retain real peer38E sync.
        await p.send(0x38e,bytes(54)+b'\\1'+bytes(7))
        assert(await q.until(0x4e3)).payload==struct.pack('>QB',a,1)
        await p.send(0x4e2,b'\\0')
        assert(await p.until(0x4e3)).payload==struct.pack('>QB',a,0)
        assert(await q.until(0x4e3)).payload==struct.pack('>QB',a,0)
        out['checks'].append('actual38E and4E2 active switches retain matching peer4E3 on two LuCiel actors')
        run=DungeonRun(34710,str(uuid.uuid4()));""")
source=source.replace("h.H/'normal-party-precheck.json'", "h.H/'party-candidate.json'")
exec(compile(source,str(h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/precheck_party.py'),'exec'),globals())
