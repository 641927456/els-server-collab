from pathlib import Path
import asyncio,hashlib,importlib.util,json,os,socket,subprocess,sys,time,traceback,uuid
R=Path('G:/els');N=Path(__file__).resolve().parent;T=N.parent
read=lambda p:json.loads(Path(p).read_bytes());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
point=read(R/'releases/local/current.json');runtime=R/point['path'];sys.dont_write_bytecode=True;sys.path[:0]=[str(runtime),str(runtime/'tools'),str(R/'tools/pylibs')]
from els_server.application import Application
from els_server.transport import GameServer
from els_server.config import ServerConfig
from els_server.storage.lifecycle import prepare_database
from els_server.friends_bridge import Bridge,BridgeConfig
sp=importlib.util.spec_from_file_location('owned_gear_QA',T/'delivery-v3/qa_worker.py');worker=importlib.util.module_from_spec(sp);sp.loader.exec_module(worker)
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str),'utf8')
async def main():
 result=dict(ok=False,physical_input_actions=0,production_database_access=False,client_copied=False,background_client_GUI_verified=False)
 root=N/'private-store';assert not root.exists();root.mkdir();logs=root/'logs';logs.mkdir();f=(logs/'events.jsonl').open('w',encoding='utf8',buffering=1)
 def log(event,**fields):f.write(json.dumps(dict(event=event,**fields),default=str)+'\n')
 cert=R/'analysis/luciel-natural-dynamic-passive-01a1531c-20261020-v1/party-UI-r10/tls';config=ServerConfig(mode='friends',port=0,state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',tls_cert=cert/'server-cert.pem',tls_key=cert/'server-key.pem',log_dir=logs,normal_equipment_moves_enabled=True)
 prepare_database(config.state_file);app=Application(config);server=None;bridge=None;probe=None;cfg=None;started=False;setup=False
 try:
  await app.start();started=True;server=GameServer(config,app,log);_,port=await server.start()
  cf=root/'server.toml';cf.write_text('[server]\nmode="friends"\nport=0\nstate_file="'+config.state_file.as_posix()+'"\naccounts_file="'+config.accounts_file.as_posix()+'"\ntls_cert="'+config.tls_cert.as_posix()+'"\ntls_key="'+config.tls_key.as_posix()+'"\nlog_dir="'+logs.as_posix()+'"\nnormal_equipment_moves_enabled=true\n','utf8')
  operation=uuid.uuid4().hex;cfg=dict(root=str(root),work=str(root/'backups'/T.name/('public-QA-'+operation)),config=str(cf),operation=operation,release=T.name,private=True)
  owned=worker.execute(cfg,'setup');setup=True;credentials=read(Path(cfg['work'])/'credentials.private.json')
  result.update(runtime=point['release'],runtime_manifest_sha256=point['manifest_sha256'],own_actor=owned['uid'])
  # Fixture production uses the original box protocol on this exact disposable role.
  import struct
  helper=R/'analysis/native-reuse-continuation-20261019-v1/protocol_helpers.py';sp=importlib.util.spec_from_file_location('owned_fixture_peer',helper);h=importlib.util.module_from_spec(sp);sp.loader.exec_module(h)
  from els_server.protocol.protocol_codec import Event,encode_frame,encode_event
  from els_server.domain.town_travel import catalog as towns
  from els_server.domain.equipment_requirements import inspect_requirements
  class FixturePeer(h.Peer):
   async def send(self,kind,payload=b'',event_id=0x202):
    e=Event(event_id,kind=kind,payload=payload,performers=(0,)if kind in(0x28,0x225,0x227,0x196)else())
    self.writer.write(encode_frame(encode_event(e),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
  fixture_bridge=Bridge(BridgeConfig('127.0.0.1',port,credentials['account']['name'],credentials['account']['token'],credentials['pin']),log);fixture_peer=None
  try:
   fixture_peer=await FixturePeer.open(fixture_bridge);await fixture_peer.roster();xyz=towns()['towns']['20000']['xyz']
   for k,a,p in ((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',owned['uid'])),(0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),(0x225,0x226,struct.pack('>iB',20000,0)),(0x227,0x228,struct.pack('>fffBH',*xyz,0,0))):
    await fixture_peer.send(k,p);await fixture_peer.until(a)
   before=worker.execute(cfg,'snapshot-box-before');box=next(i for i in before['items']if i['template']==723680)
   await fixture_peer.send(0x196,struct.pack('>QBBBIi',box['uid'],0,0,0,0,0));ack=await fixture_peer.until(0x197);assert ack.payload[:4]==bytes(4)
   snapshot=worker.execute(cfg,'snapshot-native-fixture');gears=sorted((i for i in snapshot['items']if 721881<=i['template']<=721940),key=lambda i:i['template']);assert len(gears)==4
   fixture=dict(owner=owned['uid'],items=snapshot['items'],balances=snapshot['balances'],gears=[dict(item=i,equipment_slot=inspect_requirements(i['template'],1)['equipment_slot'])for i in gears],box_preparation='Original196 on own QA, before native login; not claimed native box UI')
   write(N/'fixture.json',fixture)
  finally:
   if fixture_peer:await fixture_peer.close()
   await fixture_bridge.close()
   async with asyncio.timeout(15):
    while server.connections:await asyncio.sleep(.05)
   await app.call(lambda:None)

  bridge=Bridge(BridgeConfig('127.0.0.1',port,credentials['account']['name'],credentials['account']['token'],credentials['pin']),log);await bridge.start()
  client=Path('D:/艾尔之光/data/x2_dx11.exe');probe_path=runtime/'tools/probe_updated_client.py'
  from launch_client import COMMON_FLAGS
  settings=dict(runtime=str(runtime),client=str(client),client_sha256=sha(client),formal_probe_sha256=sha(probe_path),probe_args=['--client',str(client),*COMMON_FLAGS,'--remote-bridge'])
  write(N/'settings.json',settings);write(N/'authorization.json',dict(user_request='你后台启动客户端验证一下，不要控制我的键盘鼠标',scope='One fresh original client process on a never-switched private desktop and UI-restricted job; no OS input, no user process attachment, no client copy, private own QA only',runtime=point['release']))

  sys.path.insert(0,str(T));import native_acceptance as acceptance
  fixture=read(N/'fixture.json');primary_snapshot=None
  for phase in ('primary','cold'):
   env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';out=(N/(phase+'-probe-console.log')).open('w',encoding='utf8')
   boundary=time.time();probe=await asyncio.create_subprocess_exec(sys.executable,'-B','-X','utf8',str(N/'probe_isolated.py'),stdout=out,stderr=subprocess.STDOUT,env=env)
   start=time.monotonic();queued=False;accepted=False;phase_result=None;phase_error=None;selected_run=None
   try:
    while probe.returncode is None and time.monotonic()-start<260:
     traces=sorted(p for p in (N/'native-log').glob('*/trace.jsonl')if p.stat().st_mtime>=boundary)
     if traces:
      trace=traces[-1];meta=trace.parent/'client-process.json'
      if not meta.exists()or read(meta)['created']<boundary-1:await asyncio.sleep(.2);continue
      selected_run=trace.parent;events=[]
      for line in trace.read_text('utf8',errors='replace').splitlines():
       try:events.append(json.loads(line).get('payload',{}))
       except ValueError:pass
      assert not any(e.get('event')in('dialog','native_fatal')for e in events),'Unexpected native dialog'
      fatal=[e for e in events if e.get('event')in('native_gear_flow_error','native_gear_cold_error')];assert not fatal,fatal[-1:] if fatal else None
      ready=any(e.get('event')=='updated_field_frame'and str(e.get('uid'))==str(owned['uid'])for e in events)
      if ready and not queued:
       selected_fixture=fixture if phase=='primary'else dict(owner=owned['uid'],items=primary_snapshot['items'])
       (trace.parent/'probe-extension.js').write_text(acceptance.source(selected_fixture,phase),'utf8');queued=True
      completed=[e for e in events if e.get('event')==('native_gear_flow_complete'if phase=='primary'else'native_gear_cold_complete')]
      if completed:
       assert len(completed)==1
       snapshot=worker.execute(cfg,'snapshot-native-'+phase)
       if phase=='primary':
        phase_result=acceptance.primary(fixture,completed[0],snapshot);primary_snapshot=snapshot
       else:
        details=[]
        for line in (N/'model-failure-detail.jsonl').read_text('utf8').splitlines():
         e=json.loads(line).get('payload',{})
         if e.get('event')=='original_item_DTO'and e.get('client_phase')==phase:details.append(e)
        phase_result=acceptance.cold(primary_snapshot,completed[0],snapshot,details)
       write(N/(phase+'-window-safety.json'),acceptance.window_safety(read(meta)['pid']))
       write(N/(phase+'-acceptance.json'),dict(**phase_result,client=read(meta),elapsed_seconds=round(time.monotonic()-start,2)));accepted=True;break
     await asyncio.sleep(.25)
    assert accepted,'Native phase did not complete before deadline: '+phase
   except BaseException:
    phase_error=traceback.format_exc();raise
   finally:
    if selected_run:(selected_run/'client.stop').write_text('Owned '+phase+' validation finished','utf8')
    if probe.returncode is None:
     try:await asyncio.wait_for(probe.wait(),25)
     except asyncio.TimeoutError:probe.terminate();await probe.wait()
    out.close()
    if(N/'isolation-receipt.json').exists():write(N/(phase+'-isolation-receipt.json'),read(N/'isolation-receipt.json'))
    write(N/(phase+'-phase.json'),dict(accepted=accepted,error=phase_error,probe_returncode=probe.returncode))
   assert probe.returncode==0
   await bridge.close();bridge=None
   async with asyncio.timeout(15):
    while server.connections:await asyncio.sleep(.05)
   await app.call(lambda:None)
   if phase=='primary':
    bridge=Bridge(BridgeConfig('127.0.0.1',port,credentials['account']['name'],credentials['account']['token'],credentials['pin']),log);await bridge.start()
  result.update(ok=True,background_client_GUI_verified=True,controlled_native_callbacks=True,natural_mouse_clicks_tested=False,primary=read(N/'primary-acceptance.json'),cold=read(N/'cold-acceptance.json'))
 except BaseException:result['error']=traceback.format_exc();raise
 finally:
  if probe and probe.returncode is None:probe.terminate();await probe.wait()
  if bridge:await bridge.close()
  if server:
   end=time.monotonic()+15
   while server.connections and time.monotonic()<end:await asyncio.sleep(.1)
   await app.call(lambda:None)
  if cfg and Path(cfg['work']).exists():
   cfg['cleanup_private_barrier_passed']=not bool(server.connections if server else True)
   try:result['terminal']=worker.execute(cfg,'terminal')
   except BaseException:result['cleanup_error']=traceback.format_exc()
  if server:await server.close()
  if started:app.close()
  f.close();result['own_QA_cleaned']=bool(result.get('terminal',{}).get('own_accounts_cleaned'));result['capacity_verified']=bool(result.get('terminal',{}).get('registration_capacity_verified'));write(N/'result.json',result)
  print(json.dumps({k:result.get(k)for k in('probe_returncode','elapsed_seconds','own_QA_cleaned','capacity_verified','background_client_GUI_verified','error','cleanup_error')},ensure_ascii=False))
asyncio.run(main())
