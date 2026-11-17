from pathlib import Path
import ast,hashlib,json
W=Path(__file__).resolve().parent;p=W/'verify_economy_tls.py';s=p.read_bytes().decode('utf8').replace('\r\n','\n')
start=s.index("            stage='guild-agit-native-movement'")
kick=s.index("            stage='transfer-kick-in-agit'")
end=s.index("            stage='disband-recreate'",kick)
tail=s.index("            report['ok']=True",end)
setup='''            def assets():
                with closing(sqlite3.connect(cfg.state_file))as db:
                    return [(load_items(db,uid),db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uid,)).fetchone(),db.execute('SELECT town,board,progress,x,y,z FROM location WHERE uid=?',(uid,)).fetchone())for uid in uids]
            before=assets()
'''
checks='''            assert assets()==before
            assert app.playing[identities[0]['id']].phase=='town_ready'
            assert app.playing[identities[1]['id']].phase=='town_ready'
            assert guild_cold(cfg.state_file,uids[0],identities[0]['id'])is None
            report['steps'].append('Kicked GuildAgit actor receives284 and remains connected; bank still refuses; actual4FE/225/227 returns to the saved town with all original assets unchanged')
'''
s=s[:start]+setup+s[kick:end]+checks+s[tail:]
s=s.replace("OUT/'economy-tls.json'","OUT/'revocation-tls.json'").replace("'economy-tls-'","'revocation-tls-'")
old="            if not report['ok']:report['worker_errors']=[r for r in logs if 'error'in r.get('event','')][-5:]"
new="            report['worker_errors']=[r for r in logs if 'error'in r.get('event','')]\n            if report['worker_errors']:report['ok']=False"
assert s.count(old)==1;s=s.replace(old,new);ast.parse(s)
target=W/'verify_revocation_tls.py';assert not target.exists();target.write_bytes(s.encode('utf8'))
print(json.dumps(dict(prepared=True,source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),fixture='Reuse normal authenticated guild setup; exercise only transferred-master kick in ready GuildAgit, guarded bank refusal and original return',natural_GUI=False)))
