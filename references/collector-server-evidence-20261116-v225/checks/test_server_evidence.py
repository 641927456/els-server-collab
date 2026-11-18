"""In-process collector checks: no client, server listener or player DB."""
import ast
import asyncio
from contextlib import contextmanager
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
import argparse
options = argparse.ArgumentParser(add_help=False)
options.add_argument('--runtime', type=Path, required=True)
arguments, remaining = options.parse_known_args()
sys.argv[1:] = remaining
RUNTIME = arguments.runtime.resolve(strict=True)
sys.path[:0]=[str(RUNTIME),str(RUNTIME/'vendor')]
import els_server
els_server.__path__.insert(0,str(ROOT/'source/els_server'))
from els_server import diagnostic_reports as reports
from els_server.gameplay_diagnostics import SessionDiagnostics,IncidentHistory

ACCOUNT=7
SESSION='a'*32
CLIENT=dict(schema=1,session_id=SESSION,events=[],client_delivery=dict(events=[dict(phase='ready')]))

def event(name='protocol_error',**fields):
    return dict(event=name,account_id=ACCOUNT,diagnostic_session=SESSION,connection=3,
                phase='dungeon_active',dungeon=34320,stage=3,part=0,**fields)

def summary(rows,client=None):
    return dict(diagnostic_session=SESSION,classification=client or reports.classify(
        {'run/gameplay-errors.json':json.dumps(CLIENT).encode()}),server_context=rows)

def archive(client=None,**extra):
    document=dict(schema=1,attempt_id='b'*32,diagnostic_session=SESSION,**extra)
    members={'summary.json':json.dumps(document).encode(),
             'run/gameplay-errors.json':json.dumps(client or CLIENT).encode()}
    members['manifest.json']=json.dumps(dict(schema=1,files={k:hashlib.sha256(v).hexdigest()for k,v in members.items()})).encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_STORED)as output:
        for name,raw in members.items():output.writestr(name,raw)
    return stream.getvalue()

class MemoryStore(reports.ReportStore):
    def __init__(self,root):
        super().__init__(root)
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE reports(id TEXT PRIMARY KEY,account_id INTEGER,request_id TEXT,digest TEXT,size INTEGER,created REAL,summary TEXT,UNIQUE(account_id,request_id))')

    @contextmanager
    def database(self):
        with self.db:yield self.db

    def close(self):
        super().close();self.db.close()

class ServerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'checks',prefix='owned-unit-')
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to((ROOT/'checks').resolve()))
        self.store=MemoryStore(self.temp.name)

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def accept(self,rows,body=None):
        body=body or archive()
        return self.store.accept(ACCOUNT,'c'*32,hashlib.sha256(body).hexdigest(),body,rows)

    def test_synthetic_mixed_observations_reclassify_without_root_cause(self):
        original = summary([
            event('request_timing', kind=0xbb, failed=True),
            event(error='Synthetic lease/lifecycle error'),
            event(error='Synthetic transport close after failure'),
        ])
        frozen = copy.deepcopy(original)
        result = reports.classified_summary(original, ACCOUNT)['classification']
        self.assertEqual(original, frozen)
        self.assertEqual(result['client_classification']['code'], 'gameplay_observation_only')
        self.assertEqual(result['code'], 'server_error_observed')
        self.assertEqual(result['server_signals'], {'request_timing': 1, 'protocol_error': 2})
        self.assertFalse(result['root_cause_confirmed'])

    def test_upload_list_read_replay_agree(self):
        result=self.accept([event(error='C1 HP instance lease/phase changed')])
        self.assertEqual(result['classification']['code'],'server_error_observed')
        listed=self.store.list()[0]['summary']['classification']
        read=self.store.read(result['report_id'])['summary']['classification']
        # A duplicate uses the persisted report, not a later empty snapshot.
        replay=self.accept([])
        self.assertTrue(replay['duplicate'])
        self.assertEqual(result['classification'],listed)
        self.assertEqual(listed,read)
        self.assertEqual(read,replay['classification'])
        with self.assertRaisesRegex(ValueError,'request_conflict'):
            self.accept([],archive(description='different body'))

    def test_old_report_read_reclassifies_without_rewriting_storage(self):
        result=self.accept([event(error='original failure')])
        raw=self.store.db.execute('SELECT summary FROM reports').fetchone()[0]
        old=json.loads(raw);old['classification']=old['classification']['client_classification']
        old_raw=json.dumps(old)
        with self.store.db:self.store.db.execute('UPDATE reports SET summary=?',(old_raw,))
        self.assertEqual(self.store.list()[0]['summary']['classification']['code'],'server_error_observed')
        self.assertEqual(self.store.read(result['report_id'])['summary']['classification']['code'],'server_error_observed')
        self.assertEqual(self.accept([])['classification']['code'],'server_error_observed')
        self.assertEqual(self.store.db.execute('SELECT summary FROM reports').fetchone()[0],old_raw)

    def test_cross_account_and_cross_attempt_evidence_excluded(self):
        foreign=[{**event(), 'account_id':8},{**event(),'diagnostic_session':'d'*32}]
        result=self.accept(foreign)
        self.assertEqual(result['classification']['code'],'gameplay_observation_only')
        self.assertEqual(self.store.read(result['report_id'])['summary']['server_context'],[])
        for session in (None,'invalid'):
            value=summary([event()]);value['diagnostic_session']=session
            self.assertEqual(reports.classified_summary(value,ACCOUNT)['classification']['code'],'gameplay_observation_only')

    def test_client_cannot_inject_server_error(self):
        body=archive(payload={'server_context':[event()]},server_context=[event()],classification={'code':'server_error_observed'})
        self.assertEqual(self.accept([],body)['classification']['code'],'gameplay_observation_only')

    def test_each_server_failure_signal_promotes(self):
        for name in ('protocol_error','worker_error','connection_error','notification_error','connection_timeout','request_timing'):
            with self.subTest(name=name):
                row=event(name,failed=True)
                self.assertEqual(reports.classified_summary(summary([row]),ACCOUNT)['classification']['code'],'server_error_observed')

    def test_expected_rejection_slow_request_and_normal_exit_are_not_faults(self):
        rows=[event('gameplay_result_nonzero',result=1369),event('business_rejection'),
              event('request_timing',failed=False,total_ms=1700),event('connection_eof'),event('connection_finished')]
        self.assertEqual(reports.classified_summary(summary(rows),ACCOUNT)['classification']['code'],'gameplay_observation_only')

    def test_client_error_preserved_and_summary_idempotent(self):
        client=reports.classify({'run/gameplay-errors.json':json.dumps({**CLIENT,'events':[dict(signal='native_exception')]}).encode()})
        result=reports.classified_summary(summary([event()],client),ACCOUNT)
        self.assertEqual(result['classification']['client_classification'],client)
        self.assertEqual(reports.classified_summary(result,ACCOUNT),result)

    def test_server_text_redaction_and_summary_bound(self):
        rows=[event(error='token=private-fixture-value',packet='private-packet')for _ in range(24)]
        result=reports.classified_summary(summary(rows),ACCOUNT)
        self.assertNotIn('private-fixture-value',json.dumps(result))
        self.assertNotIn('private-packet',json.dumps(result))
        self.assertEqual(result['classification']['server_observations'],24)
        self.assertEqual(len(result['classification']['server_errors']),8)
        self.assertEqual(result['classification']['server_errors_omitted'],16)

    def test_protocol_handler_collects_exception_provenance(self):
        tree=ast.parse((ROOT/'source/els_server/transport.py').read_text('utf8'))
        handler=next(n for n in ast.walk(tree)if isinstance(n,ast.ExceptHandler)
                     and isinstance(n.type,ast.Tuple)and [x.id for x in n.type.elts]==['ProtocolError','SessionOrderError'])
        journal=SessionDiagnostics(3);captured=[]
        session=SimpleNamespace(account=SimpleNamespace(uid=45),phase='dungeon_active',role='game',active_map=1,dungeon_run=SimpleNamespace(identity=34320,stage=3,part=0))
        try:raise RuntimeError('C1 HP instance lease/phase changed token=private-fixture-value')
        except RuntimeError as error:
            scope=dict(self=SimpleNamespace(metrics={'protocol_errors':0}),error=error,journal=journal,
                       business=session,identity={'id':ACCOUNT},sessionlog=lambda event,**kw:captured.append((event,kw)))
            exec(compile(ast.fix_missing_locations(ast.Module(body=handler.body,type_ignores=[])),'<actual-protocol-handler>','exec'),scope)
        name,fields=captured[0]
        self.assertEqual(name,'protocol_error')
        self.assertTrue(fields['exception']['frames'])
        self.assertTrue(fields['source_stack'])
        self.assertEqual(len(fields['exception']['frames'][-1]['code_sha256']),64)
        history=IncidentHistory();history.record(name,{**fields,'diagnostic_session':SESSION})
        result=reports.classified_summary(summary(history.snapshot(ACCOUNT,SESSION)),ACCOUNT)
        self.assertTrue(result['server_context'][0]['exception']['frames'])
        self.assertNotIn('private-fixture-value',json.dumps(result))

    def test_upload_service_logs_server_and_preserves_client_signal(self):
        async def run():
            client={**CLIENT,'events':[dict(signal='native_exception')]}
            body=archive(client);logs=[];replies=[]
            service=reports.UploadService(self.temp.name,lambda event,**kw:logs.append((event,kw)),lambda account,session:[event(error='server failure')])
            service.store=self.store
            async def job(function,*args):return function(*args)
            service._store_job=job
            async def call(function,*args):return {'id':ACCOUNT}
            async def write(writer,value):replies.append(dict(value))
            reader=asyncio.StreamReader();reader.feed_data(body);reader.feed_eof()
            app=SimpleNamespace(call=call,registry=SimpleNamespace(authenticate=lambda:None))
            request=dict(op='report',name='fixture',token='fixture',size=len(body),sha256=hashlib.sha256(body).hexdigest(),request_id='c'*32,diagnostic_session=SESSION)
            with patch('els_server.friends_wire.write_json',write):
                await service.handle(app,reader,None,request,'fixture')
            self.assertTrue(replies[-1]['ok'])
            self.assertEqual({name for name,_ in logs},{'client_gameplay_error_report','server_gameplay_error_report'})
            self.assertEqual(service.active,0)
        asyncio.run(run())

if __name__=='__main__':unittest.main(verbosity=2)
