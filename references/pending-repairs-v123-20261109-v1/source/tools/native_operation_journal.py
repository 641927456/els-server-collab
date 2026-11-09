"""Bounded host observations of component-initiated native calls.

This journal records asynchronous observations, not a native execution trace.
It never reads a pointer, infers object generations, or controls the process.
"""
from collections import OrderedDict, deque
from math import isfinite
from re import fullmatch
from threading import RLock
from hashlib import sha256


class NativeOperationJournal:
    history_limit = 128
    pending_limit = 64
    source_scope = 'native_cache_sync component-initiated calls only'

    def __init__(self):
        self._lock = RLock()
        self._recent = deque(maxlen=self.history_limit)
        self._unreturned = OrderedDict()
        self._sources = OrderedDict()
        self._received = 0
        self._accepted = 0
        self._invalid = 0
        self._validation_errors = {}
        self._evictions = dict(history=0, return_not_observed=0, source_sequence_states=0)
        self._sequence_counts = dict(gap_events=0, missing_sequence_slots=0,
                                     duplicate_events_within_history=0, out_of_order_events=0)
        self._pairing = dict(begin_key_already_unmatched=0, terminal_without_observed_begin=0,
                             terminal_metadata_mismatch=0, terminal_sequence_not_after_begin=0)

    @staticmethod
    def _validate(payload):
        if type(payload) is not dict:
            return 'payload_type'
        if type(payload.get('event')) is not str or payload['event'] != 'component_native_operation':
            return 'event'
        if type(payload.get('component')) is not str or payload['component'] != 'native_cache_sync':
            return 'component'
        for name in ('script_instance', 'operation'):
            value = payload.get(name)
            if type(value) is not str or not 1 <= len(value) <= 128:
                return name
        for name in ('id', 'sequence', 'thread'):
            value = payload.get(name)
            if type(value) is not int or not 1 <= value <= 2**53 - 1:
                return name
        if type(payload.get('phase')) is not str or payload['phase'] not in ('begin', 'return', 'throw'):
            return 'phase'
        for name in ('rva', 'arg0'):
            value = payload.get(name)
            if type(value) is not str or fullmatch(r'0x[0-9a-fA-F]{1,16}', value) is None:
                return name
        value = payload.get('timestamp')
        if type(value) not in (int, float) or not 0 <= value <= 2**53 - 1 or not isfinite(value):
            return 'timestamp'
        value = payload.get('dropped_in_script')
        if type(value) is not int or not 0 <= value <= 2**53 - 1:
            return 'dropped_in_script'
        return None

    def record(self, payload) -> None:
        with self._lock:
            self._received += 1
            error = self._validate(payload)
            if error is not None:
                self._invalid += 1
                self._validation_errors[error] = self._validation_errors.get(error, 0) + 1
                return
            row = {name: payload[name] for name in (
                'event', 'component', 'script_instance', 'id', 'sequence', 'phase',
                'thread', 'rva', 'operation', 'arg0', 'timestamp', 'dropped_in_script')}
            row['received_sequence'] = self._received
            self._accepted += 1
            source_key = (row['script_instance'], row['component'])
            source = self._sources.get(source_key)
            duplicate = any((old['script_instance'], old['component']) == source_key
                            and old['sequence'] == row['sequence'] for old in self._recent)
            if source is None:
                if len(self._sources) == self.history_limit:
                    self._sources.popitem(last=False)
                    self._evictions['source_sequence_states'] += 1
                source = dict(script_instance=row['script_instance'], component=row['component'],
                              first_sequence=row['sequence'], last_sequence=row['sequence'],
                              highest_sequence=row['sequence'], **dict.fromkeys(self._sequence_counts, 0))
                self._sources[source_key] = source
            else:
                self._sources.move_to_end(source_key)
                highest = source['highest_sequence']
                if row['sequence'] > highest + 1:
                    self._sequence_counts['gap_events'] += 1
                    source['gap_events'] += 1
                    missing = row['sequence'] - highest - 1
                    self._sequence_counts['missing_sequence_slots'] += missing
                    source['missing_sequence_slots'] += missing
                if row['sequence'] < highest:
                    self._sequence_counts['out_of_order_events'] += 1
                    source['out_of_order_events'] += 1
                source['last_sequence'] = row['sequence']
                source['highest_sequence'] = max(highest, row['sequence'])
            if duplicate:
                self._sequence_counts['duplicate_events_within_history'] += 1
                source['duplicate_events_within_history'] += 1

            key = (row['script_instance'], row['component'], row['id'])
            begin = self._unreturned.get(key)
            if row['phase'] == 'begin':
                if begin is not None:
                    self._pairing['begin_key_already_unmatched'] += 1
                else:
                    if len(self._unreturned) == self.pending_limit:
                        self._unreturned.popitem(last=False)
                        self._evictions['return_not_observed'] += 1
                    self._unreturned[key] = row
            elif begin is None:
                self._pairing['terminal_without_observed_begin'] += 1
            elif any(row[name] != begin[name] for name in ('thread', 'rva', 'operation', 'arg0')):
                self._pairing['terminal_metadata_mismatch'] += 1
            elif row['sequence'] <= begin['sequence']:
                self._pairing['terminal_sequence_not_after_begin'] += 1
            else:
                del self._unreturned[key]
            if len(self._recent) == self.history_limit:
                self._evictions['history'] += 1
            self._recent.append(row)

    def snapshot(self, trigger, thread=None) -> dict:
        with self._lock:
            unmatched = [dict(row) for row in self._unreturned.values()]
            return dict(
                event='component_operation_context', trigger=trigger,
                first_writer_identified=False, transport_complete=False,
                source_scope=self.source_scope, object_generation_evidence=False,
                history_limit=self.history_limit, pending_limit=self.pending_limit,
                received_events=self._received, accepted_events=self._accepted,
                validation_errors=dict(total=self._invalid, by_field=dict(self._validation_errors)),
                recent=[dict(row) for row in self._recent],
                return_not_observed=unmatched,
                thread_filter=thread,
                same_thread_return_not_observed=[dict(row) for row in unmatched
                                                if thread is not None and row['thread'] == thread],
                evictions=dict(self._evictions), pairing_observations=dict(self._pairing),
                source_sequence_observations=dict(self._sequence_counts),
                source_sequences=[dict(source) for source in self._sources.values()],
                sequence_tracking_limit=self.history_limit,
                duplicate_detection_history_limit=self.history_limit,
                interpretation=(
                    'Only received, validated events are retained. Return not observed may reflect '
                    'asynchronous delivery, missing events or eviction; it does not mean the call '
                    'is currently executing or caused the fault. Pointer equality is not object '
                    'generation evidence. Sequence gaps are observations, not proof of where loss '
                    'occurred; late events do not repair prior gap counts. Duplicate detection is '
                    'limited to retained history. No-message periods do not prove no execution.'),
            )


class RunContextJournal:
    """Metadata received by this host; never native memory or a UI action log."""

    history_limit = 128
    detail_limit = 64
    module_limit = 256
    thread_limit = 64
    # A presentation filter based on previous trace frequency, not protocol semantics.
    frequent_code_filter = frozenset(((0, 0), (0x202, 0x7d0),
                                     (0x202, 0x640), (0x202, 0x38e)))
    _register_names = ('rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi',
                       'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15', 'rip')
    _metrics = ('calculations', 'writes', 'total_ms', 'main_thread', 'ready_units',
                'ability_calculations', 'ability_total_ms', 'ability_outside_cache_ms',
                'final_input_writes', 'actor_base_writes', 'original_HP_clamps',
                'periodic_refresh_ms', 'power_refresh_skipped', 'ability_refresh_skipped',
                'immediate_ability_calculations', 'native_power_builds', 'complete_ability_builds',
                'hooks')

    def __init__(self):
        self._lock = RLock()
        self._received = self._accepted = self._ignored = self._invalid = 0
        self._recent = deque(maxlen=self.history_limit)
        self._detail = deque(maxlen=self.detail_limit)
        self._statuses = deque(maxlen=self.detail_limit)
        self._errors = deque(maxlen=32)
        self._stacks = deque(maxlen=8)
        self._modules = OrderedDict()
        self._threads = OrderedDict()
        self._code_threads = OrderedDict()
        self._last_fault = None
        self._last_exit = None
        self._last_exit_api_return = None
        self._last_detached = None
        self._evictions = dict(recent=0, detail=0, statuses=0, errors=0, stacks=0,
                               modules=0, observed_threads=0, code_thread_counts=0)

    @staticmethod
    def _integer(value, maximum=2**53 - 1):
        return type(value) is int and 0 <= value <= maximum

    @staticmethod
    def _timestamp(value):
        return (type(value) in (int, float) and 0 <= value <= 2**53 - 1
                and isfinite(value))

    @staticmethod
    def _pointer(value):
        return type(value) is str and fullmatch(r'0x[0-9a-fA-F]{1,16}', value) is not None

    @staticmethod
    def _tag(value):
        return type(value) is str and fullmatch(r'[A-Za-z0-9_.-]{1,128}', value) is not None

    @staticmethod
    def _error_metadata(value):
        # Error text may contain an argument or credential. Keep its identity and
        # length here; this context copy is intentionally not another text sink.
        if type(value) is not str:
            return {'text_observed': False}
        head = value.split(':', 1)[0]
        names = ('Error', 'TypeError', 'RangeError', 'ReferenceError', 'SyntaxError',
                 'EvalError', 'URIError', 'InternalError')
        return dict(text_observed=True, text_length=len(value),
                    text_sha256=sha256(value.encode('utf8', errors='replace')).hexdigest(),
                    error_name=head if head in names else 'unknown')

    def _append(self, collection, row, name):
        if len(collection) == collection.maxlen:
            self._evictions[name] += 1
        collection.append(row)

    def _count(self, mapping, key, row, limit, eviction_name):
        previous = mapping.get(key)
        if previous is None:
            if len(mapping) == limit:
                mapping.popitem(last=False)
                self._evictions[eviction_name] += 1
            mapping[key] = dict(row, observed_events=1)
        else:
            previous.update(row)
            previous['observed_events'] += 1
            mapping.move_to_end(key)

    def _fault_metadata(self, payload):
        event = payload.get('event')
        row = dict(event=event if type(event) is str and event in
                   ('original_fatal_exception', 'process_exit_requested') else 'unknown')
        for name in ('timestamp',):
            if self._timestamp(payload.get(name)):
                row[name] = payload[name]
        if self._integer(payload.get('thread')):
            row['thread'] = payload['thread']
        if self._integer(payload.get('fault_id')) and payload['fault_id'] > 0:
            row['fault_id'] = payload['fault_id']
        for name in ('address', 'caller'):
            if self._pointer(payload.get(name)):
                row[name] = payload[name]
        code = payload.get('code')
        if self._pointer(code) or self._integer(code, 0xffffffff):
            row['code'] = code
        if payload.get('api') in ('ExitProcess', 'TerminateProcess'):
            row['api'] = payload['api']
        if row['event'] == 'process_exit_requested':
            if self._pointer(payload.get('target_handle')) or payload.get('target_handle') is None:
                row['target_handle'] = payload.get('target_handle')
            if type(payload.get('target_is_current_pseudo_handle')) is bool or payload.get('target_is_current_pseudo_handle') is None:
                row['target_is_current_pseudo_handle'] = payload.get('target_is_current_pseudo_handle')
        if payload.get('capture_stage') == 'game_crash_filter':
            row['capture_stage'] = 'game_crash_filter'
        else:
            row['capture_stage'] = 'not_observed'
        if row['event'] == 'original_fatal_exception':
            registers = payload.get('registers')
            if type(registers) is not dict:
                registers = {}
            present = [name for name in self._register_names if self._pointer(registers.get(name))]
            row['registers_observed'] = len(present)
            row['registers_missing'] = [name for name in self._register_names if name not in present]
            for name in ('rip', 'rsp'):
                if name in present:
                    row[name] = registers[name]
        return row

    def record(self, message, received_at=None, script_instance=None) -> None:
        with self._lock:
            self._received += 1
            if type(message) is not dict:
                self._invalid += 1
                return
            is_error = message.get('type') == 'error'
            payload = message if is_error else message.get('payload')
            if type(payload) is not dict:
                self._invalid += 1
                return
            event = 'script_error' if is_error else payload.get('event')
            allowed = ('client_event_send', 'module_loaded', 'module_unloaded', 'script_error',
                       'native_cache_sync_ready', 'native_cache_sync_disabled', 'native_cache_sync_metrics',
                       'original_fatal_exception', 'process_exit_requested', 'original_fatal_read_error',
                       'original_fatal_stack', 'original_fatal_stack_unavailable',
                       'process_exit_api_return', 'instrumentation_detached')
            if type(event) is not str or event not in allowed:
                self._ignored += 1
                return
            row = dict(event=event, received_sequence=self._received)
            if self._timestamp(received_at):
                row['host_received_at'] = received_at
            if self._timestamp(payload.get('timestamp')):
                row['timestamp'] = payload['timestamp']
            for name, value in (('script_source', message.get('script_source')),
                                ('script_instance', script_instance or message.get('script_instance'))):
                if self._tag(value):
                    row[name] = value
            if self._integer(payload.get('thread')):
                row['thread'] = payload['thread']
            if event.startswith('original_fatal_') and self._integer(payload.get('fault_id')) and payload['fault_id'] > 0:
                row['fault_id'] = payload['fault_id']

            if event == 'client_event_send':
                if not (self._integer(payload.get('event_id'), 0xffffffff)
                        and self._integer(payload.get('event_kind'), 0xffff)):
                    self._invalid += 1
                    return
                row.update(event_id=payload['event_id'], event_kind=payload['event_kind'])
                row['omitted_from_recent_detail'] = (row['event_id'], row['event_kind']) in self.frequent_code_filter
                self._count(self._code_threads, (row['event_id'], row['event_kind'], row.get('thread')),
                            dict(event_id=row['event_id'], event_kind=row['event_kind'], thread=row.get('thread'),
                                 last_received_sequence=row['received_sequence'],
                                 last_source_timestamp=row.get('timestamp'), last_host_received_at=row.get('host_received_at')),
                            self.history_limit, 'code_thread_counts')
                if not row['omitted_from_recent_detail']:
                    self._append(self._detail, row, 'detail')
            elif event in ('module_loaded', 'module_unloaded'):
                name, base, size = payload.get('name'), payload.get('base'), payload.get('size')
                if not (self._tag(name) and self._pointer(base) and self._integer(size, 2**64 - 1)
                        and size > 0 and int(base, 16) + size <= 2**64):
                    self._invalid += 1
                    return
                row.update(name=name, base=base, size=size)
                key = int(base, 16)
                if event == 'module_loaded':
                    if key not in self._modules and len(self._modules) == self.module_limit:
                        self._modules.popitem(last=False)
                        self._evictions['modules'] += 1
                    self._modules[key] = row
                    self._modules.move_to_end(key)
                else:
                    current = self._modules.get(key)
                    row['matched_observed_load'] = (current is not None and current['name'] == name
                                                    and current['size'] == size)
                    if row['matched_observed_load']:
                        del self._modules[key]
            elif event == 'script_error' or event == 'original_fatal_read_error':
                row['error'] = self._error_metadata(payload.get('description') if is_error else payload.get('error'))
                for name in ('lineNumber', 'columnNumber'):
                    if self._integer(payload.get(name)):
                        row[name] = payload[name]
                self._append(self._errors, row, 'errors')
            elif event.startswith('native_cache_sync_'):
                for name in self._metrics:
                    if self._integer(payload.get(name)):
                        row[name] = payload[name]
                if event == 'native_cache_sync_disabled':
                    row['error'] = self._error_metadata(payload.get('reason'))
                self._append(self._statuses, row, 'statuses')
            elif event in ('original_fatal_stack', 'original_fatal_stack_unavailable'):
                row['available'] = event == 'original_fatal_stack'
                if self._integer(payload.get('requested_bytes')):
                    row['requested_bytes'] = payload['requested_bytes']
                if event == 'original_fatal_stack':
                    raw = payload.get('hex')
                    row['bytes'] = len(raw) // 2 if type(raw) is str and len(raw) % 2 == 0 else None
                    row['available'] = row['bytes'] is not None
                    row['byte_count_basis'] = 'hex string length only; bytes not retained or validated'
                else:
                    row['error'] = self._error_metadata(payload.get('error'))
                self._append(self._stacks, row, 'stacks')
            elif event == 'process_exit_api_return':
                if payload.get('api') != 'TerminateProcess' or type(payload.get('result')) is not int or not -2**31 <= payload['result'] < 2**31:
                    self._invalid += 1
                    return
                row.update(api='TerminateProcess', result=payload['result'])
                self._last_exit_api_return = row
            elif event == 'instrumentation_detached':
                if self._tag(payload.get('reason')):
                    row['reason'] = payload['reason']
                else:
                    row['reason'] = 'unknown'
                if type(payload.get('crash_present')) is bool:
                    row['crash_present'] = payload['crash_present']
                self._last_detached = row
            else:
                row.update(self._fault_metadata(payload))
                if event == 'original_fatal_exception':
                    self._last_fault = row
                else:
                    self._last_exit = row

            if 'thread' in row:
                self._count(self._threads, row['thread'],
                            dict(thread=row['thread'], last_event=event,
                                 last_received_sequence=row['received_sequence'],
                                 last_source_timestamp=row.get('timestamp'), last_host_received_at=row.get('host_received_at')),
                            self.thread_limit, 'observed_threads')
            self._accepted += 1
            self._append(self._recent, row, 'recent')

    def _module_for(self, fault, caller=False):
        address = fault.get('caller') if caller else fault.get('rip') or fault.get('address')
        if not self._pointer(address):
            return dict(status='unknown', reason='exit caller not observed' if caller else 'fault RIP/address not observed')
        found = [row for base, row in self._modules.items()
                 if base <= int(address, 16) < base + row['size']]
        if len(found) != 1:
            return dict(status='unknown', reason='no unique retained loaded module range', address=address)
        row = found[0]
        if ('timestamp' in row and 'timestamp' in fault and row['timestamp'] > fault['timestamp']):
            return dict(status='unknown', reason='observed load timestamp is after fault', address=address)
        return dict(status='observed_loaded_range', address=address, name=row['name'],
                    base=row['base'], size=row['size'], rva=hex(int(address, 16) - int(row['base'], 16)),
                    basis='received module metadata; asynchronous delivery is not an atomic loader snapshot')

    def _latest_fault_stack_status(self):
        fault = self._last_fault
        if not fault or 'script_instance' not in fault or 'fault_id' not in fault:
            return dict(status='unknown', reason='latest fault has no complete script_instance/fault_id key')
        matches = [row for row in self._stacks
                   if row.get('script_instance') == fault['script_instance']
                   and row.get('fault_id') == fault['fault_id']]
        identity = dict(script_instance=fault['script_instance'], fault_id=fault['fault_id'])
        if not matches:
            return dict(status='unknown', reason='no retained stack observation matches the exact fault key', **identity)
        return dict(status='matched', basis='same script_instance and fault_id',
                    matched_observations=len(matches), latest_stack_observation=dict(matches[-1]), **identity)

    def snapshot(self, trigger, fault=None) -> dict:
        from copy import deepcopy
        with self._lock:
            supplied = self._fault_metadata(fault) if type(fault) is dict else None
            current = supplied if supplied is not None else self._last_fault
            current = current or {}
            fault_time = current.get('timestamp')
            details = []
            for original in self._detail:
                row = dict(original)
                if self._timestamp(fault_time) and 'timestamp' in row:
                    row['source_timestamp_minus_trigger_ms'] = row['timestamp'] - fault_time
                if self._last_fault and 'timestamp' in self._last_fault and 'timestamp' in row:
                    row['source_timestamp_minus_fault_ms'] = row['timestamp'] - self._last_fault['timestamp']
                details.append(row)
            fault_exit_delta = None
            if (self._last_fault and self._last_exit and 'timestamp' in self._last_fault
                    and 'timestamp' in self._last_exit):
                fault_exit_delta = self._last_exit['timestamp'] - self._last_fault['timestamp']
            return deepcopy(dict(
                event='run_error_context', trigger=trigger, transport_complete=False,
                first_writer_identified=False, native_write_history_available=False,
                replayable_operations_available=False, ui_semantics_available=False,
                observed_threads_are_all_process_threads=False,
                received_messages=self._received, accepted_events=self._accepted,
                ignored_messages=self._ignored, invalid_messages=self._invalid,
                limits=dict(history=self.history_limit, recent_detail=self.detail_limit,
                            modules=self.module_limit, observed_threads=self.thread_limit,
                            code_thread_counts=self.history_limit, statuses=self.detail_limit, errors=32, stacks=8),
                evictions=dict(self._evictions), recent=list(self._recent),
                recent_client_detail=details,
                frequent_code_filter=[dict(event_id=a, event_kind=b) for a, b in sorted(self.frequent_code_filter)],
                frequent_code_filter_basis='presentation filter from prior observed frequency; not a protocol periodicity claim',
                code_thread_counts=list(self._code_threads.values()), observed_threads=list(self._threads.values()),
                retained_loaded_modules=list(self._modules.values()),
                triggering_fault=current or None,
                fault_module=self._module_for(current if current.get('event') == 'original_fatal_exception'
                                              else self._last_fault or current),
                latest_observed_fault=self._last_fault, latest_observed_exit=self._last_exit,
                latest_observed_exit_api_return=self._last_exit_api_return,
                exit_api_return_association='no call ID: an observed return is not automatically paired to the latest exit request',
                exit_target_scope='Only the reported current-process pseudo-handle is identified; other real handles are not resolved to this process.',
                exit_caller_module=self._module_for(self._last_exit or {}, caller=True),
                latest_instrumentation_detached=self._last_detached,
                exit_minus_fault_source_ms=fault_exit_delta,
                stack_observations=list(self._stacks),
                latest_fault_stack_status=self._latest_fault_stack_status(),
                stack_association='Only the same script_instance and positive fault_id are matched; legacy events without this key remain unknown.',
                script_errors=list(self._errors), native_cache_status=list(self._statuses),
                interpretation='Only received metadata is retained. A send entry does not prove delivery or a UI action. '
                               'Last observed activity is not a thread liveness or blocking determination. '
                               'Module lifetimes and event order may be incomplete; no native write history or replayable operation sequence is recorded.',
            ))
