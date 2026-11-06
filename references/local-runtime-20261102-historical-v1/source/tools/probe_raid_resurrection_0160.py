"""Read-only 0x160 probe over the server's structured JSONL log.

Classifies resurrection_diagnostic rows by native payload size (A7=34, 160=18,
AA=0), prints live rows and summarizes whether a raid window really routed
revival through the server wire. The log has no dungeon id, so run the probe for
the exact test window; when several clients are online pass --connection.

Usage:
  python tools/probe_raid_resurrection_0160.py --follow
  python tools/probe_raid_resurrection_0160.py --since-minutes 30
  python tools/probe_raid_resurrection_0160.py --since-minutes 30 --json
"""
import argparse
import datetime
import json
import sys
import time
from pathlib import Path

# Native request sizes from els_server/protocol/known_resurrection.py.
KINDS = {0: '0xaa death-complete', 18: '0x160 use-stone', 34: '0xa7 death-request'}


def log_files(directory):
    current = directory / 'server.jsonl'
    backups = sorted(directory.glob('server.jsonl.*'),
                     key=lambda path: int(path.suffix[1:]), reverse=True)
    return [*backups, current]


def classify(payload_bytes):
    if not isinstance(payload_bytes, int) or payload_bytes < 0:
        return 'unknown'
    return KINDS.get(payload_bytes, 'unknown-%d' % payload_bytes)


def parse(line):
    line = line.strip()
    if not line:
        return None
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


def event_time(row):
    try:
        return datetime.datetime.fromisoformat(row['time'])
    except (KeyError, TypeError, ValueError):
        return None


class Report:
    def __init__(self):
        self.rows = []
        self.counts = {name: 0 for name in KINDS.values()}
        self.counts.update({'unknown': 0})
        self.accepted = 0
        self.rejected = 0
        self.rejections = {}

    def add(self, row, kind):
        self.rows.append((event_time(row), row.get('connection'), row.get('phase'), kind,
                          row.get('results'), row.get('rejection')))
        self.counts[kind] = self.counts.get(kind, 0) + 1
        if kind == '0x160 use-stone':
            results = row.get('results') or []
            if any(code == 0 for code in results):
                self.accepted += 1
            else:
                self.rejected += 1
                reason = row.get('rejection') or 'no ack result logged'
                self.rejections[reason] = self.rejections.get(reason, 0) + 1

    def summary(self):
        deaths = self.counts['0xa7 death-request']
        completes = self.counts['0xaa death-complete']
        uses = self.counts['0x160 use-stone']
        if uses and self.accepted:
            verdict = ('客户端发送 0x160 且服务端成功回包：团本复活走服务端复活链，'
                       '声明上限可以生效')
        elif uses:
            verdict = ('客户端会发送 0x160，但本次全部被拒：需按 rejection 补团本复活授权')
        elif deaths or completes:
            verdict = ('只看到 A7/AA，没有 0x160：复活由客户端原生本地执行，服务端无法限次')
        else:
            verdict = '窗口内没有任何复活事件（未死亡或未进入团本）'
        return dict(deaths=deaths, completes=completes, uses=uses,
                    uses_accepted=self.accepted, uses_rejected=self.rejected,
                    rejections=self.rejections, verdict=verdict)


def print_row(line):
    stamp = line[0].isoformat() if line[0] else '?'
    results = line[4] if line[4] is not None else '-'
    rejection = ('  reject=%s' % line[5]) if line[5] else ''
    print('%s conn=%s phase=%s %-22s ack=%s%s' % (stamp, line[1], line[2], line[3], results, rejection))


def print_summary(report, args):
    summary = report.summary()
    print('\n== 团本 0x160 实测汇总 ==')
    print('日志目录: %s' % args.log_dir.resolve())
    if args.connection is not None:
        print('连接过滤: conn=%s' % args.connection)
    print('A7=%d  AA=%d  160=%d (成功 %d / 拒绝 %d)' % (
        summary['deaths'], summary['completes'], summary['uses'],
        summary['uses_accepted'], summary['uses_rejected']))
    for reason, count in sorted(summary['rejections'].items()):
        print('拒绝原因: %s ×%d' % (reason, count))
    print('结论: %s' % summary['verdict'])
    print('注意: 服务端日志不含 dungeon id，请确保窗口内只有目标团本会话，或用 --connection 限定。')
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def rows_from(line, connection):
    row = parse(line)
    if row is None or row.get('event') != 'resurrection_diagnostic':
        return None
    if connection is not None and row.get('connection') != connection:
        return None
    return row


def analyze(args):
    cutoff = None
    if args.since_minutes is not None:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=args.since_minutes)
    report = Report()
    for path in log_files(args.log_dir):
        if not path.is_file():
            continue
        with path.open(encoding='utf8', errors='replace') as stream:
            for line in stream:
                row = rows_from(line, args.connection)
                if row is None:
                    continue
                stamp = event_time(row)
                if cutoff is not None and (stamp is None or stamp < cutoff):
                    continue
                kind = classify(row.get('payload_bytes', -1))
                report.add(row, kind)
                if not args.json:
                    print_row(report.rows[-1])
    print_summary(report, args)


def follow(args):
    report = Report()
    path = log_files(args.log_dir)[-1]
    path.parent.mkdir(parents=True, exist_ok=True)
    offset = path.stat().st_size if path.is_file() else 0
    print('跟踪 %s，从此处开始记录；按 Ctrl+C 结束并打印汇总。' % path.resolve())
    try:
        while True:
            if not path.is_file():
                time.sleep(0.5)
                continue
            size = path.stat().st_size
            if size < offset:
                offset = 0
            with path.open('rb') as stream:
                stream.seek(offset)
                chunk = stream.read()
            if not chunk:
                time.sleep(0.5)
                continue
            if not chunk.endswith(b'\n'):
                cut = chunk.rfind(b'\n')
                if cut < 0:
                    time.sleep(0.5)
                    continue
                chunk = chunk[:cut + 1]
            offset += len(chunk)
            for line in chunk.decode('utf8', 'replace').splitlines():
                row = rows_from(line, args.connection)
                if row is None:
                    continue
                kind = classify(row.get('payload_bytes', -1))
                report.add(row, kind)
                if not args.json:
                    print_row(report.rows[-1])
                    sys.stdout.flush()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print_summary(report, args)


def main():
    parser = argparse.ArgumentParser(description='团本 0xA7/0xAA/0x160 复活链路实测探针')
    parser.add_argument('--log-dir', type=Path, default=Path('logs/server'),
                        help='包含 server.jsonl 的日志目录（默认 logs/server）')
    parser.add_argument('--since-minutes', type=float, default=None,
                        help='只分析最近 N 分钟的事件')
    parser.add_argument('--connection', type=int, default=None,
                        help='只分析指定连接号')
    parser.add_argument('--follow', action='store_true', help='从文件末尾开始实时跟踪')
    parser.add_argument('--json', action='store_true', help='只输出 JSON 汇总')
    args = parser.parse_args()
    if args.follow:
        follow(args)
    else:
        analyze(args)


if __name__ == '__main__':
    main()
