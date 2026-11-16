from pathlib import Path
import ast,hashlib,json,shutil
W=Path(__file__).resolve().parent;C=W/'candidate';F=W/'test-full-source';O=W/'revocation-fix-v1';assert not O.exists();O.mkdir()
changes={
'els_server/domain/guild_periodic.py':("    from els_server.domain.guild_services import synchronize\n", "    context=getattr(s,'guild_agit',None)\n    if context is not None and context.get('revoked'):return []\n    from els_server.domain.guild_services import synchronize\n"),
'els_server/domain/guild_appearance.py':("    if s.phase!='guild_agit_ready':return\n", "    if s.phase!='guild_agit_ready'or s.guild_agit.get('revoked'):return\n"),
'els_server/application.py':("                 self.application.world.dungeons.room(self))\n", "                 self.application.world.dungeons.room(self),\n                 bool(getattr(self,'guild_agit',None)and self.guild_agit.get('revoked')))\n")}
rows=[]
for name,(before,after)in changes.items():
 p=C/name;raw=p.read_bytes();s=raw.decode('utf8').replace('\r\n','\n');assert s.count(before)==1,name
 q=O/'before'/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(raw)
 s=s.replace(before,after);ast.parse(s);p.write_bytes(s.encode('utf8'))
 target=F/name;target.unlink();shutil.copy2(p,target)
 rows.append(dict(path=name,before_sha256=hashlib.sha256(raw).hexdigest(),after_sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
m=F/'rollup-manifest.json';value=json.loads(m.read_bytes())
for row in value['files']:
 if row['path']in changes:
  p=F/row['path'];row.update(size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
m.write_bytes((json.dumps(value,indent=2)+'\n').encode('utf8'))
(O/'source-change.json').write_bytes((json.dumps(dict(files=rows,baseline_failure=str(W/'economy-tls.json'),cause='A committed kick revokes membership but keeps the original loaded scene until native4FE return; guild-specific passive refresh used a member-only guard before queued284 delivery',
    fix='Skip only guild-specific periodic/appearance refresh for the already-revoked context and invalidate paused periodic steps on that actual transition; keep all economic guards and native return proof',installed=False),indent=2)+'\n').encode('utf8'))
print(json.dumps(dict(ok=True,files=len(rows),installed=False,normal_return_and_economic_guards_unchanged=True)))
