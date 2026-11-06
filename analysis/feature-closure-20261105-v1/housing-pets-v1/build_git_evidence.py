"""Prepare source and sanitized QA evidence; never includes databases or traces."""
from pathlib import Path
import ast,hashlib,json,sys,time
sys.path.insert(0,'G:/els/tools/pylibs')
import psutil

H=Path(__file__).resolve().parent
N=H/'native-game-v1'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
manifest=read(H/'candidate-v4.manifest.json')
files=manifest['files']
for rel,sha in files.items():
    p=H/'candidate-v4'/rel
    assert digest(p)==sha,rel
    ast.parse(p.read_bytes(),str(p))

checks=(
 ('codec-native-1793943008395519700.json','Original placement readers; 512 primitive input cases and 0/1/4 records'),
 ('entry-native-1793943378104225600.json','Full original924 reader, including 0/1/4 placements; shared A3B reader'),
 ('mat-admission-1793948662143319500.json','Six original mats; normal small NPC stock and price; five owned-only mats; nonprojecting free-position mats rejected'),
 ('writer-TLS-1793948960990565600.json','Final authenticated grid-placement writer, free-position rejection, ordinary owned-pet support preserved, replay, ownership, slot limit, occupied mat, rollback, expiry and summon reconciliation'),
 ('actual-packets-native-1793944497692865100.json','15 actual authenticated TLS payloads consumed by original readers'),
 ('contract-deadlines-1793949000223012700.json','Final seven-day cutoff and permanent upgrade; explicit storage clocks and valid grid mats'),
 ('population-native-1793945297105753400.json','Original92F reader, nonempty self record and public equipment'),
 ('population-TLS-1793945548789159100.json','Actual92E immediately after923; current SQL profile and malformed/stale rejection'),
 ('population-actual-native-1793945644602926900.json','Three actual92F payloads consumed by original reader'),
 ('furniture-native-1793948091282452000.json','Original924 reader and runtime layout copy preserve nonempty modern furniture; model creation is a separate path'),
)
evidence=[]
for name,scope in checks:
    p=H/name;v=read(p);assert v['ok'],name
    evidence.append(dict(file=name,sha256=digest(p),ok=True,scope=scope,
                         native_Game=v.get('native_Game',False)))

attempt=N/'family1-v7'
scene=read(attempt/'scenario-complete.json')
native=read(attempt/'native-observer-complete.json')
server=read(attempt/'server-result.json')
isolation=read(attempt/'isolation-receipt.json')
assert scene['ok']and native['ok']and server['ok']
assert native['seconds']>=120 and native['original_self_actor']and native['original_placed_pet_entity']and native['original_retrieved_entity']
job_pids=set(isolation['job_membership_at_game_birth']['actual']['pids'])|set(isolation['own_job_pids_before_close'])
assert not any(psutil.pid_exists(pid)for pid in job_pids)
assert isolation['physical_input_actions']==0 and isolation['input_desktop_unchanged']and isolation['client_executable_unchanged']
assert isolation['selected_signed_payload']=='a33de4e7abdc18f8e35bd2a64e7dba92b76036d710f06354c615778df9c5eb0e'
assert not scene['errors']and not scene['placed']and scene['phase']=='housing_ready'
assert {0x923,0x92e,0xa38,0xa3a}.issubset({r['kind']for r in scene['events']})
summary=dict(ok=True,source_sha256=files,source_files=len(files),dependency_PR=892,
 dependency_head='5367cd0123ec0e1bbe765687a8f33ccd612f6a57',
 previous_evidence=evidence,
 correction='92E is original room population, not a house-exit request. The old deadline report label is not reused as exit evidence.',
 native=dict(clients=1,original_Game=True,natural_GUI=False,physical_input_actions=0,
  seconds=native['seconds'],frames=native['frames'],original_self_actor=True,
  original_placed_pet_entity=True,original_retrieved_entity=True,
  original_pending_gates=native['pending_gates'],
  source_manifest='candidate-v2.manifest.json',
  source_reuse='Native case uses v2. Final v4 rejects nonprojecting free-position mats, removes their selector and restores the original shared owned-pet support reader. The successful grid input path is unchanged; final authenticated writer/deadline tests cover the changed branches.',
  actor_identity='Native factory result+270 matches current NativeUser; Game+8 matches returned actor',
  pet_entity_key='Original2451350 and2460890 use selected mat item UID, not character UID',
  tested_requests=['923','92E','A38','A3A'],server_errors=0,
  early_retrieval_growth_unchanged=True,ED_XP_inventory_unchanged=True,saved_ordinary_town_unchanged=True,
  signed_runtime_payload=isolation['selected_signed_payload'],
  original_executable_sha256=isolation['client_sha256_after'],
  observer_sha256=digest(attempt/'observer-input.js'),backend_sha256=digest(attempt/'server_input.py'),
  harness_sha256=digest(attempt/'probe_owned.py'),input_desktop_unchanged=True,owned_job_empty=True,
  guard_status_after_Game_exit=isolation.get('guard_closed'),guard_startup_selftest=isolation['guard_startup_selftest']),
 failed_cases_retained=[
  dict(attempt='family1',reason='Preparation fixture requested town20001 but had not seeded the saved town; Game not started'),
  dict(attempt='family1-v2',reason='Observer treated actor+48 as UID; original actor identity resides through actor+270'),
  dict(attempt='family1-v3',reason='Observer searched pet manager using character UID; original key is mat item UID'),
  dict(attempt='family1-v4',reason='Free-position mat did not bind the original pet mat'),
  dict(attempt='family1-v5',reason='Frame sampling confirms free-position mat UID remains zero'),
  dict(attempt='family1-v6',reason='Free-position furniture model exists but does not bind the pet mat; fixed with original grid placement and v3 rejection')],
 exclusions=['Natural GUI','Foreign housing visits','Housing expansion','Native house exit','Pet Battle combat'],
 private_evidence='Original binaries, runtime traces, accounts, TLS credentials and databases stay private and are not submitted.',
 main_merged=False,installed=False,public_progress_updated=False)
out=H/('qualified-summary-'+str(time.time_ns())+'.json')
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
entries=[dict(path=rel,mode='100644',type='blob',content=(H/'candidate-v4'/rel).read_text('utf8'))for rel in files]
qa=['verify_codec_native.py','verify_entry_native.py','verify_mat_admission.py','verify_writer_tls.py',
    'verify_actual_packets.py','verify_contract_deadlines.py','verify_population_native.py',
    'verify_population_tls.py','verify_population_actual.py','verify_furniture_native.py',
    'candidate-v2.manifest.json','candidate-v3.manifest.json','candidate-v4.manifest.json',
    'build_git_evidence.py','REVIEW.md']
qa_paths=[(H/name,'analysis/feature-closure-20261105-v1/housing-pets-v1/'+name)for name in qa]
qa_paths +=[(N/name,'analysis/feature-closure-20261105-v1/housing-pets-v1/native-game-v1/'+name)
           for name in ('observer.js','server_owned.py','prepare_attempt.py')]
qa_paths.append((out,'analysis/feature-closure-20261105-v1/housing-pets-v1/'+out.name))
for p,path in qa_paths:
    entries.append(dict(path=path,mode='100644',type='blob',content=p.read_text('utf8')))
(H/'git-elements-v2.json').write_text(json.dumps(entries,ensure_ascii=False),'utf8')
print(json.dumps(dict(ok=True,files=len(entries),source_files=len(files),summary=out.name,summary_sha256=digest(out))))
