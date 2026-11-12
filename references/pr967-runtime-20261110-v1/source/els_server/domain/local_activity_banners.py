"""Local-only extra activity rows for the client's activity strip.

The original ``0x2af`` record shape is reused verbatim; only the local ID
namespace, texts, countdown and optional reward preview differ. Nothing here
opens a campaign, grants a reward, or claims retail identity - these rows are
pure display entries an operator asked for, kept in ``config/local-banners.json``
so they can be edited without touching code.

A malformed or missing file is not fatal: the session simply gets no extra
rows and the installed activity flow keeps working untouched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from els_server.paths import PROJECT_ROOT
from els_server.protocol.access_event_2026 import ActivityRecord, activity_list_update

PATH = PROJECT_ROOT / 'config/local-banners.json'

# Local ID namespace, clearly outside any recovered retail key/code pair.
_BASE = 20261100
MAX_BANNERS = 8
MAX_TITLE = 40
MAX_SUBTITLE = 60
MAX_DESCRIPTION = 80
MAX_MINUTES = 5256000  # 10 years in minutes, still exact in float32


def _text(row, field, limit, *, required):
    value = row.get(field, '')
    if type(value) is not str:
        raise ValueError(f'活动横幅 {field} 必须是文本')
    if len(value) > limit:
        raise ValueError(f'活动横幅 {field} 超过 {limit} 字')
    if required and not value.strip():
        raise ValueError(f'活动横幅 {field} 不能为空')
    return value


def _integer(row, field, low, high):
    value = row.get(field, 0)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'活动横幅 {field} 需要是 {low}–{high} 的整数')
    return value


def build(rows):
    """Validate operator rows and return immutable ActivityRecord entries."""
    if type(rows) is not list:
        raise ValueError('活动横幅必须是列表')
    if len(rows) > MAX_BANNERS:
        raise ValueError(f'活动横幅最多 {MAX_BANNERS} 条')
    records = []
    for index, row in enumerate(rows):
        if type(row) is not dict:
            raise ValueError('活动横幅条目必须是对象')
        item = _integer(row, 'item', 0, 2**31 - 1)
        count = _integer(row, 'count', 0, 99)
        if item and not count:
            raise ValueError('活动横幅填写了奖励道具就必须填写数量')
        if count and not item:
            raise ValueError('活动横幅填写了数量就必须填写奖励道具')
        records.append(ActivityRecord(
            key=-(_BASE + index),
            code=_BASE + index,
            text_08=_text(row, 'title', MAX_TITLE, required=True),
            float_28=float(_integer(row, 'minutes', 1, MAX_MINUTES)),
            text_2c=_text(row, 'subtitle', MAX_SUBTITLE, required=False),
            text_4c=_text(row, 'description', MAX_DESCRIPTION, required=False),
            int_6c=0,
            map_70=((item, count, 0),) if item else (),
            category_80=7,
            float_84=0.,
            float_88=0.,
            bits_8c=0,
            bits_94=0,
            int_9c=0,
            bool_a0=False,
            pair_a1=(0, 0),
        ))
    for record in records:
        record.encode()  # Fail early instead of mid-packet.
    return tuple(records)


def load(path):
    data = json.loads(Path(path).read_bytes())
    if type(data) is not dict or set(data) != {'schema_version', 'banners'}:
        raise ValueError('活动横幅配置字段不正确')
    if data['schema_version'] != 1:
        raise ValueError('活动横幅配置版本不支持')
    return build(data['banners'])


def _plain(rows):
    """Normalised operator rows, safe to hand back to the GM panel."""
    out = []
    for row in rows:
        if type(row) is not dict:
            continue
        out.append(dict(title=row.get('title', ''), subtitle=row.get('subtitle', ''),
                        description=row.get('description', ''), minutes=row.get('minutes', 43200),
                        item=row.get('item', 0), count=row.get('count', 0)))
    return out


def snapshot(path):
    try:
        data = json.loads(Path(path).read_bytes())
    except (OSError, ValueError):
        data = dict(schema_version=1, banners=[])
    rows = data.get('banners') if isinstance(data, dict) else []
    return dict(schema_version=1, rows=_plain(rows if isinstance(rows, list) else []),
                limits=dict(count=MAX_BANNERS, title=MAX_TITLE, subtitle=MAX_SUBTITLE,
                            description=MAX_DESCRIPTION, minutes=MAX_MINUTES))


def update(path, value):
    # reason/operation_id are the GM request envelope; they are ignored here.
    if type(value) is not dict or not {'banners'} <= set(value) <= {'banners', 'reason', 'operation_id'}:
        raise ValueError('活动横幅提交字段不正确')
    rows = value['banners']
    build(rows)  # Full validation before any write.
    payload = dict(schema_version=1, banners=_plain(rows))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix('.tmp')
    with tmp.open('w', encoding='utf8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(target)
    return snapshot(path)


class BannerSource:
    """Re-reads the file only when its mtime changes, so edits need no restart."""

    def __init__(self, path):
        self.path = Path(path)
        self._stamp = None
        self._rows = ()

    def rows(self):
        try:
            stamp = self.path.stat().st_mtime
        except OSError:
            self._stamp, self._rows = None, ()
            return ()
        if stamp != self._stamp:
            self._stamp = stamp
            try:
                self._rows = load(self.path)
            except Exception:
                self._rows = ()  # Never block a login on a bad banner file.
        return self._rows


class BannerFlow:
    """Delegates the installed activity flow and appends the extra rows once."""

    def __init__(self, inner, source):
        self._inner = inner
        self._source = source
        self._sent = None
        self._rows = ()

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def finalize(self, session, replies):
        replies = self._inner.finalize(session, replies)
        if getattr(session, 'phase', None) not in ('town_ready', 'dungeon_active'):
            return replies
        rows = self._source.rows()
        signature = tuple(record.encode() for record in rows)
        if self._sent == signature:
            return replies
        extra = []
        if self._rows:
            # Retract the previous set so an edit replaces instead of piling up.
            extra.append(activity_list_update(action=2, records=self._rows))
        self._sent, self._rows = signature, rows
        if rows:
            extra.append(activity_list_update(action=1, records=rows))
        return list(replies) + extra
