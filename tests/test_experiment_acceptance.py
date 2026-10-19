"""Acceptance regression checks using real recorded evidence and negative controls."""
import copy,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from verify_experiment import evaluate

def load(folder):
    return ([json.loads(l) for l in (folder/'launch-loopback-trace.jsonl').read_text(encoding='utf8').splitlines()],
            json.loads((folder/'launch-loopback.json').read_text()),
            json.loads((folder/'local-bootstrap.json').read_text()))

positive=load(BASE/'analysis/runs/20261012-140230-597200')
negative=load(BASE/'analysis/runs/20261012-140504-086254')
assert evaluate(*positive)['bootstrap_key_exchange_verified']
assert evaluate(*negative)['tcp_redirect_verified']
assert not evaluate(*negative)['bootstrap_key_exchange_verified']
trace,probe,capture=positive
assert not evaluate([],probe,capture)['tcp_redirect_verified']
assert not evaluate(trace,probe,{'bind':['127.0.0.1',19400],'connections':[]})['tcp_redirect_verified']
wrong=copy.deepcopy(probe);wrong['pid']=-1
assert not evaluate(trace,wrong,capture)['tcp_redirect_verified']
assert not evaluate(trace+[{'type':'error','description':'synthetic interceptor failure'}],probe,capture)['startup_verified']
without_state=[r for r in trace if r.get('payload',{}).get('event')!='bootstrap_session_state']
assert not evaluate(without_state,probe,capture)['bootstrap_key_exchange_verified']
without_init=[r for r in trace if r.get('payload',{}).get('event')!='client_event_send']
assert not evaluate(without_init,probe,capture)['bootstrap_key_exchange_verified']
assert not evaluate(*positive)['account_login_verified']
generated=load(BASE/'analysis/runs/20261012-141735-264199')
bad_mac=load(BASE/'analysis/runs/20261012-141842-855611')
assert evaluate(*generated)['independent_bootstrap_codec_verified']
assert evaluate(*bad_mac)['tcp_redirect_verified']
assert not evaluate(*bad_mac)['bootstrap_key_exchange_verified']
assert not evaluate(*bad_mac)['independent_bootstrap_codec_verified']
trace,probe,capture=generated
no_plaintext=[r for r in trace if r.get('payload',{}).get('direction')!='plaintext_in']
assert not evaluate(no_plaintext,probe,capture)['independent_bootstrap_codec_verified']
unverified=copy.deepcopy(capture);unverified['connections'][0]['decoded_events'][0]['mac_verified']=False
assert not evaluate(trace,probe,unverified)['independent_bootstrap_codec_verified']
no_heartbeat=copy.deepcopy(capture);no_heartbeat['connections'][0]['decoded_events']=no_heartbeat['connections'][0]['decoded_events'][:1]
assert not evaluate(trace,probe,no_heartbeat)['independent_bootstrap_codec_verified']
assert not evaluate(*generated)['account_login_verified']
character=load(BASE/'analysis/runs/20261012-160040-757711')
assert evaluate(*character)['character_list_verified']
incomplete=load(BASE/'analysis/runs/20261012-155827-327121')
assert evaluate(*incomplete)['local_login_verified']
assert not evaluate(*incomplete)['character_list_verified']
trace,probe,capture=character
for missing in ['character_full_dto_parsed','character_list_payload_parsed','character_list_handler_return']:
    shortened=[r for r in trace if r.get('payload',{}).get('event')!=missing]
    assert not evaluate(shortened,probe,capture)['character_list_verified']
empty=copy.deepcopy(trace)
for r in empty:
    if r.get('payload',{}).get('event')=='character_list_handler_return':r['payload']['character_count']=0
assert not evaluate(empty,probe,capture)['character_list_verified']
mixed=incomplete[0]+[r for r in character[0] if r.get('payload',{}).get('event') in ['character_full_dto_parsed','character_list_payload_parsed','character_list_handler_return']]
assert not evaluate(mixed,incomplete[1],incomplete[2])['character_list_verified']
wrong_state=copy.deepcopy(trace)
for r in wrong_state:
    if r.get('payload',{}).get('event')=='character_list_handler_return':r['payload']['state']='0xdeadbeef'
assert not evaluate(wrong_state,probe,capture)['character_list_verified']
print('PASS: generated bootstrap, sequence/MAC rejection, real local login and character creation, negative parser/object evidence controls.')
