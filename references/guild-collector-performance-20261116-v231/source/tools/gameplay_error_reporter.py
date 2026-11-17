"""Bounded background reports using existing authenticated diagnostic upload.

Failure evidence uses bounded read-only snapshots; no player inputs or new hooks.
"""
import asyncio
from collections import OrderedDict, deque
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import threading
import time
import uuid
import zipfile
from copy import deepcopy

from friends_diagnostics import clean_text, clean_values, diagnostic_sanitize, encode, upload
from els_server.diagnostic_reports import validate_archive
from els_server.gameplay_diagnostics import normal_native_dialog
from native_failure_evidence import FailureEvidence, bounded, bound_row


def now():
    return datetime.now(timezone.utc).isoformat()


def _stack_adapter_fault(value):
    return (value.get('event') in ('local_stack_template_caps', 'local_shortcut_exact_total')
            and value.get('status') in ('guard-rejected', 'prefix-timeout'))


def signal_for(message):
    if not isinstance(message, dict):
        return None
    if message.get('type') in ('error', 'extension_error'):
        return 'support_error'
    value = message.get('payload')
    if not isinstance(value, dict):
        return None
    event = value.get('event', '')
    if event == 'original_fatal_exception':
        return 'native_exception'
    if event in ('dialog', 'resource_native_dialog'):
        if normal_native_dialog(value):return None
        if isinstance(value.get('text'),str) and not value['text'].strip():return 'blank_dialog'
        return 'native_dialog'
    if event == 'gameplay_abnormal_exit':
        return 'abnormal_exit'
    if event == 'instrumentation_detached' and value.get('crash_present') is True:
        return 'observer_crash'
    if _stack_adapter_fault(value) or (
            isinstance(event, str) and event.endswith(('_error', '_failed', '_failure', '_disabled', '_rejected'))):
        return 'support_fault'
    return None


def observation(message, signal, run_context, operations, token):
    value = message.get('payload') if isinstance(message.get('payload'), dict) else message
    row = dict(signal=signal, observed_utc=now())
    # Do not copy packets, registers, memory, arbitrary arguments, or raw stacks.
    for key in ('event', 'timestamp', 'thread', 'code', 'address', 'api', 'caller', 'fault_id',
                'text', 'title', 'description', 'error', 'reason', 'lineNumber',
                'columnNumber', 'exit_code', 'error_type', 'game_alive', 'frida_version'):
        item = value.get(key)
        if type(item) in (str, int, float, bool):
            row[key] = item[:1024] if isinstance(item, str) else item
    for key in ('script_source', 'script_instance', 'script_sha256'):
        if isinstance(message.get(key), str):
            row[key] = message[key][:128]
    if _stack_adapter_fault(value):
        row['status'] = value['status']
        if isinstance(value.get('error'), str):
            row['error'] = clean_text(value['error'], [token])[:1024]
    if value.get('event') == 'native_startup_failed':
        if isinstance(value.get('phase'),str):row['phase'] = value['phase'][:64]
        row['visibility_ready'] = value.get('visibility_ready') is True
        checks = value.get('mismatches')
        if isinstance(checks, list):
            import re
            row['mismatches'] = [dict(rva=item['rva'],expected=item['expected'],actual=item['actual'])
                for item in checks[:64] if isinstance(item,dict) and type(item.get('rva')) is int
                and 0 <= item['rva'] < 2**32
                and all(isinstance(item.get(key),str) and re.fullmatch('[a-f0-9]{16}',item[key])
                        for key in ('expected','actual'))]
    if value.get('event') == 'native_activity_guide_error':
        from native_operation_journal import RunContextJournal
        record = RunContextJournal()._fault_metadata(dict(value,event='original_fatal_exception'))
        row['native_exception_context'] = record
        if type(value.get('stage')) is int:row['stage'] = value['stage']
        if type(value.get('show')) is bool:row['show'] = value['show']
    state = run_context()
    row['context'] = {key: state[key] for key in (
        'fault_module', 'latest_fault_stack_status', 'received_messages',
        'ignored_messages', 'invalid_messages', 'evictions') if key in state}
    if signal == 'native_exception':
        row['context']['exception_context'] = state.get('triggering_fault')
    if signal in ('abnormal_exit', 'observer_crash'):
        for key in ('latest_observed_exit', 'exit_caller_module',
                    'latest_observed_exit_api_return', 'latest_instrumentation_detached'):
            if state.get(key) is not None:
                row['context'][key] = state[key]
    row['context']['native_cache_status'] = state.get('native_cache_status', [])[-8:]
    if (message.get('script_source') == 'host_probe'
            and value.get('description') == 'Native startup preparation not observed before deadline'
            and state.get('latest_native_startup_step') is not None):
        row['context']['latest_native_startup_step'] = state['latest_native_startup_step']
    row['context']['recent_client_detail'] = state.get('recent_client_detail', [])[-16:]
    calls = operations()
    row['component_calls'] = [{key: call[key] for key in (
        'component', 'script_instance', 'sequence', 'phase', 'operation', 'rva',
        'thread', 'timestamp') if key in call} for call in calls.get('recent', [])[-16:]]
    row['root_cause_confirmed'] = False
    if message.get('type')=='error':
        from friends_diagnostics import script_frames
        row.update(script_frames(message.get('stack')))
    row['observation_limit'] = 'Recent sends and component calls do not prove delivery or cause.'
    row = clean_values(diagnostic_sanitize(row), [token])
    if len(encode(row)) > 16000:
        row['context'].pop('recent_client_detail', None)
        row['component_calls'] = []
        row['details_omitted_for_size'] = True
    return row


def archive_bytes(session_id, started, document, runtime):
    from els_server.diagnostic_reports import classify
    members = {
        'attempt.json': encode(dict(schema=1, attempt_id=session_id,
                                    started_utc=started, ended_utc=now(), phase='gameplay_observation')),
        'run/gameplay-errors.json': encode(document),
    }
    members['summary.json'] = encode(dict(schema=1, attempt_id=session_id,
        created_utc=now(), payload=runtime, description='',
        collection='automatic_gameplay_errors', classification=classify(members)))
    members['manifest.json'] = encode(dict(schema=1, files={
        key: hashlib.sha256(value).hexdigest() for key, value in members.items()}))
    result = io.BytesIO()
    # Stored text also avoids pathological compression ratios for repetitive errors.
    with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, value in members.items():
            archive.writestr(name, value)
    body = result.getvalue()
    validate_archive(body)
    return body


class GameplayErrorReporter:
    batch_delay = 3.0
    max_uploads = 5  # Four live batches and one final batch; matches server hourly quota.

    def __init__(self, run, config, runtime, run_context, operations, send=upload,session_id=None):
        self.run = Path(run)
        self.request = {key: getattr(config, key) for key in
                        ('host', 'port', 'name', 'token', 'certificate_sha256')}
        self.runtime = runtime
        self.failure_evidence = FailureEvidence()
        self.context = run_context
        self.operations = operations
        self.send = send
        self.session_id = session_id or uuid.uuid4().hex
        self.request['diagnostic_session']=self.session_id
        self.started = now()
        self.condition = threading.Condition()
        self.rows = deque(maxlen=32)
        self.pending = deque(maxlen=32)
        self.seen = OrderedDict()
        self.counts = dict(observed=0, duplicates=0, history_omitted=0, upload_attempts=0)
        self.capture_window = time.monotonic()
        self.capture_count = 0
        self.urgent_signals = set()
        self.counts['capture_rate_omitted'] = 0
        self.stopping = False
        self.dirty = False
        self.delivery_pending=False
        from client_delivery_journal import ClientDeliveryJournal
        self.delivery=ClientDeliveryJournal();self.delivery_flush=0.
        self.worker = threading.Thread(target=self._run, name='gameplay-error-reports', daemon=True)
        self.worker.start()

    def capture_host_failure(self):
        try:self.failure_evidence.capture_host(self.runtime)
        except Exception as error:
            self.failure_evidence.host=dict(status="capture_failed",error_type=type(error).__name__)

    def observe(self, message):
        self.failure_evidence.observe(message)
        value=message.get('payload') if isinstance(message,dict) else None
        if isinstance(value,dict)and value.get('event')=='client_delivery_trace':
            with self.condition:
                if self.stopping:return
                if self.delivery.record(message):
                    self.delivery_pending=True
                    if time.monotonic()-self.delivery_flush>=3:
                        self.delivery_flush=time.monotonic();self.dirty=True;self.condition.notify()
            return
        if isinstance(value,dict) and value.get('event') in ('original_fatal_stack','original_fatal_stack_unavailable'):
            with self.condition:
                if self.stopping:return
                for row in reversed(self.rows):
                    if (row.get('signal')=='native_exception' and type(row.get('fault_id')) is int
                        and row['fault_id']>0 and row['fault_id']==value.get('fault_id')
                        and row.get('script_instance')==message.get('script_instance')):
                        metadata=self.context().get('latest_fault_stack_status')
                        row['context']['latest_fault_stack_status']=clean_values(diagnostic_sanitize(metadata),[self.request['token']])
                        extra={key:bounded(value[key]) for key in ('stack_candidates','read_errors') if key in value}
                        row['context'].setdefault('failure_evidence',{}).update(clean_values(diagnostic_sanitize(extra),[self.request['token']]))
                        bound_row(row)
                        if not any(old is row for old in self.pending):self.pending.append(row)
                        self.dirty=True;self.condition.notify();break
            return
        signal = signal_for(message)
        if signal is None:
            return
        value = message.get('payload') if isinstance(message.get('payload'), dict) else message
        identity = {}
        for key in ('event', 'code', 'address', 'text', 'description', 'error', 'reason',
                    'lineNumber', 'columnNumber', 'exit_code'):
            item = value.get(key)
            if type(item) in (str, int, float, bool):
                identity[key] = item[:1024] if isinstance(item, str) else item
        if _stack_adapter_fault(value):
            identity['status'] = value['status']
        identity.update(signal=signal, script_source=message.get('script_source'),script_sha256=message.get('script_sha256'))
        if signal=='native_exception' and type(value.get('fault_id')) is int and value['fault_id']>0:
            identity.update(fault_id=value['fault_id'],script_instance=message.get('script_instance'))
        fingerprint = hashlib.sha256(encode(identity)).hexdigest()
        with self.condition:
            if self.stopping:
                return
            self.counts['observed'] += 1
            if fingerprint in self.seen:
                self.counts['duplicates'] += 1
                row=self.seen[fingerprint]
                row['occurrences']+=1
                row['last_observed_utc']=now()
                if not any(old is row for old in self.rows):
                    if len(self.rows)==self.rows.maxlen:self.counts['history_omitted']+=1
                    self.rows.append(row)
                # Preserve a changed final context without doing full snapshots
                # for every repeated error in a tight loop.
                if time.monotonic()-row['_last_capture']>=60:
                    latest=observation(message,signal,self.context,self.operations,self.request['token'])
                    row['last_context']=latest['context']
                    row['last_component_calls']=latest['component_calls']
                    row['_last_capture']=time.monotonic()
                    if not any(old is row for old in self.pending):self.pending.append(row)
            else:
                current = time.monotonic()
                if current-self.capture_window >= 60:
                    self.capture_window = current
                    self.capture_count = 0
                    self.urgent_signals.clear()
                urgent = signal in ('native_exception', 'abnormal_exit', 'observer_crash') and signal not in self.urgent_signals
                if self.capture_count >= 32 and not urgent:
                    self.counts['capture_rate_omitted'] += 1
                    self.dirty = True
                    self.condition.notify()
                    return
                self.capture_count += 1
                if urgent:
                    self.urgent_signals.add(signal)
                row = observation(message, signal, self.context, self.operations, self.request['token'])
                row['context']['failure_evidence']=clean_values(diagnostic_sanitize(self.failure_evidence.snapshot(message)),[self.request['token']])
                bound_row(row)
                row.update(fingerprint=fingerprint,occurrences=1,last_observed_utc=row['observed_utc'],_last_capture=time.monotonic())
                self.seen[fingerprint] = row
                if len(self.seen) > 128:
                    self.seen.popitem(last=False)
                if len(self.rows) == self.rows.maxlen:
                    self.counts['history_omitted'] += 1
                self.rows.append(row)
                self.pending.append(row)
            self.dirty = True
            self.condition.notify()

    def close(self, exit_code=None):
        if type(exit_code) is int and exit_code != 0:
            self.observe(dict(payload=dict(event='gameplay_abnormal_exit', exit_code=exit_code)))
        with self.condition:
            self.stopping = True
            self.condition.notify()
        # At most two 8 s OS queries, two 3 s file reads and the active/final
        # 5 s uploads can overlap shutdown. All happen after gameplay stops.
        self.worker.join(35)
        if self.worker.is_alive():
            print('ELS_GAMEPLAY_REPORT: final_upload_pending', flush=True)

    def _document(self, rows):
        return dict(schema=1, session_id=self.session_id, runtime=self.runtime,
                    updated_utc=now(), events=deepcopy([{k:v for k,v in row.items() if not k.startswith('_')} for row in rows]), counters=dict(self.counts),
                    collection='automatic_gameplay_errors', raw_memory_included=False,client_delivery=self.delivery.snapshot())

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.dirty or self.stopping)
                deadline = time.monotonic() + self.batch_delay
                while not self.stopping and time.monotonic() < deadline:
                    self.condition.wait(deadline-time.monotonic())
                final = self.stopping
                if not self.dirty and not (final and (self.pending or self.delivery_pending)):
                    if final:
                        return
                    continue
                self.dirty = False
                limit = self.max_uploads if final else self.max_uploads-1
                delivery_due=self.delivery_pending and final
                batch = self._document(self.pending) if (self.pending or delivery_due) and self.counts['upload_attempts'] < limit else None
                if batch is not None:
                    self.pending.clear()
                    self.counts['upload_attempts'] += 1
                    self.delivery_pending=False
                local = self._document(self.rows)
            try:
                self._persist(local, batch)
            except Exception as error:
                # Diagnostic I/O failure is visible, but cannot escape into gameplay.
                print('ELS_GAMEPLAY_REPORT: '+type(error).__name__, flush=True)
            if final:
                return

    def _persist(self, local, batch):
        for document in (local,batch):
            if document is None:continue
            try:self.failure_evidence.enrich(document,self.runtime)
            except Exception as error:document['failure_enrichment']=dict(status='failed',error_type=type(error).__name__)
            for row in document.get('events',[]):
                evidence=row.get('context',{}).get('failure_evidence')
                if evidence is not None:row['context']['failure_evidence']=clean_values(diagnostic_sanitize(evidence),[self.request['token']])
                bound_row(row)
        self.run.mkdir(parents=True, exist_ok=True)
        target = self.run/'gameplay-errors.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_bytes(encode(local))
        temporary.replace(target)
        if batch is None:
            return
        folder = self.run/'gameplay-reports'
        folder.mkdir(exist_ok=True)
        request_id = uuid.uuid4().hex
        archive = folder/(request_id+'.zip')
        archive.write_bytes(archive_bytes(self.session_id, self.started, batch, self.runtime))
        try:
            reply = asyncio.run(self.send(self.request, archive, request_id, timeout=5))
            receipt = dict(ok=reply.get('ok') is True, report_id=reply.get('report_id'),
                           error=reply.get('error'), request_id=request_id)
        except Exception as error:
            receipt = dict(ok=False, error=type(error).__name__, request_id=request_id)
        (folder/(request_id+'.json')).write_bytes(encode(receipt))
        print('ELS_GAMEPLAY_REPORT: '+json.dumps(receipt, ensure_ascii=True), flush=True)
