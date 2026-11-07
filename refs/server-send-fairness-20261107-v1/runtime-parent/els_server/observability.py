"""Bounded structured logs off the socket loop; no keys or packet bodies."""
import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
from collections import Counter
import queue
import sys
import threading


class EventLog:
    # Diagnostics can be summarized on overflow; operational failures retain
    # the original synchronous fallback if the bounded queue is exhausted.
    LOW_VALUE = frozenset(('client_request', 'local_business_response_sent',
                           'request_timing', 'application_timing_summary','town_positions_sent'))

    def __init__(self, config):
        config.log_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.Logger('els-server', logging.INFO)
        file = RotatingFileHandler(config.log_dir / 'server.jsonl', maxBytes=config.log_max_bytes,
                                   backupCount=config.log_backups, encoding='utf8')
        console=logging.StreamHandler(sys.stdout)
        console.addFilter(lambda record:not getattr(record,'diagnostic',False))
        for handler in (file,console):
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)
        self.queue = queue.Queue(maxsize=4096)
        self.lock = threading.Lock()
        self.dropped = Counter()
        self.closed = False
        self.batch_limit=min(65536,config.log_max_bytes//2)
        self.worker = threading.Thread(target=self._run, name='els-event-log', daemon=True)
        self.worker.start()

    @staticmethod
    def _line(event, values):
        return json.dumps({'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           'event': event, **values}, ensure_ascii=True)

    def __call__(self, event, **values):
        # Freeze mutable lists/dicts on the caller before handing them off.
        line = self._line(event, values)
        with self.lock:
            if self.closed:
                return
            try:
                self.queue.put_nowait((event,line))
                return
            except queue.Full:
                if event in self.LOW_VALUE:
                    self.dropped[event] += 1
                    return
        self.logger.info(line)

    def _overflow(self):
        with self.lock:
            dropped = dict(self.dropped)
            self.dropped.clear()
        if dropped:
            self.logger.info(self._line('log_overflow', {'dropped': dropped}))

    def _run(self):
        while True:
            batch=[self.queue.get()]
            for _ in range(63):
                if batch[-1]is None:break
                try:batch.append(self.queue.get_nowait())
                except queue.Empty:break
            try:
                self._overflow()
                parts=[];size=0;diagnostic=None
                for entry in batch:
                    if entry is None:break
                    event,line=entry;low=event in self.LOW_VALUE
                    if parts and(size+len(line)+1>self.batch_limit or low!=diagnostic):
                        self.logger.info('\n'.join(parts),extra={'diagnostic':diagnostic});parts=[];size=0
                    diagnostic=low
                    parts.append(line);size+=len(line)+1
                if parts:self.logger.info('\n'.join(parts),extra={'diagnostic':diagnostic})
                if batch[-1]is None:return
            finally:
                for _ in batch:self.queue.task_done()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
        self.queue.put(None)
        self.worker.join()
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
