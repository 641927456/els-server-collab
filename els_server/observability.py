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
                           'request_timing', 'application_timing_summary'))

    def __init__(self, config):
        config.log_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.Logger('els-server', logging.INFO)
        file = RotatingFileHandler(config.log_dir / 'server.jsonl', maxBytes=config.log_max_bytes,
                                   backupCount=config.log_backups, encoding='utf8')
        for handler in (file, logging.StreamHandler(sys.stdout)):
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)
        self.queue = queue.Queue(maxsize=4096)
        self.lock = threading.Lock()
        self.dropped = Counter()
        self.closed = False
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
                self.queue.put_nowait(line)
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
            line = self.queue.get()
            try:
                self._overflow()
                if line is None:
                    return
                self.logger.info(line)
            finally:
                self.queue.task_done()

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
