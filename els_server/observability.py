"""Bounded structured operational logs; no keys or packet bodies."""
import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import sys


class EventLog:
    def __init__(self, config):
        config.log_dir.mkdir(parents=True,exist_ok=True)
        self.logger=logging.Logger('els-server',logging.INFO)
        file=RotatingFileHandler(config.log_dir/'server.jsonl',maxBytes=config.log_max_bytes,
                                 backupCount=config.log_backups,encoding='utf8')
        for handler in (file,logging.StreamHandler(sys.stdout)):
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    def __call__(self,event,**values):
        self.logger.info(json.dumps({'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                    'event':event,**values},ensure_ascii=True))

    def close(self):
        for handler in self.logger.handlers[:]:
            handler.close();self.logger.removeHandler(handler)
