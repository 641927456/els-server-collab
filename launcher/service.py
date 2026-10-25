"""Launcher orchestration and offline, backed-up GM transactions.

Read-only inspection never initializes/migrates a player's database. Mutations
share the game server's SaveLease and the launcher's operation lock. Domain
inventory allocation and level thresholds remain the source of truth.
"""
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
import functools
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/pylibs'))
import psutil
from els_server.config import ServerConfig
from els_server.storage.lifecycle import SaveLease

ROLE_NAMES = ('', '艾索德', '爱莎', '蕾娜', '雷文', '伊芙', '澄', '艾拉', '艾丽希斯',
              '艾迪', '露／希尔', '萝丝', '艾因', '菈比', '诺亚', '莉缇娅')
BAGS = {1:'装备', 2:'饰品', 3:'材料', 4:'特殊', 5:'生活', 6:'消耗品', 7:'时装', 9:'已穿戴', 27:'时装'}
CLIENT = Path(os.environ.get('ELS_SHARE_CLIENT', 'client-not-selected/x2_dx11.exe')).resolve()
TZ = timezone(timedelta(hours=8))


def timestamp():
    return datetime.now(TZ).isoformat(timespec='seconds')


def bounded_int(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name}需要是 {low:,}–{high:,} 之间的整数')
    return value


def games():
    result = []
    for p in psutil.process_iter(['name']):
        try:
            if (p.info['name'] or '').lower() in ('x2.exe', 'x2_dx11.exe'):
                result.append(p.pid)
        except psutil.Error:
            pass
    return result


@functools.lru_cache(maxsize=1)
def item_catalog():
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, TEMPLATE_MAX_STACKS
    from els_server.domain.repair_pass import TEMPLATE as timed_pass
    from els_server.game_data import client_data
    data = client_data()
    rows = []
    for identity in sorted(VERIFIED_TEMPLATES):
        # This UI grants permanent instances only. Timed repair passes require
        # explicit expiry semantics and are deliberately absent from its list.
        if identity == timed_pass:
            continue
        try:
            definition = data.item(identity)
        except ValueError:
            continue
        group = TEMPLATE_BAG_GROUPS[identity]
        rows.append(dict(id=identity, name=definition['name'], group=group,
                         bag=BAGS.get(group, str(group)), stack=TEMPLATE_MAX_STACKS[identity],
                         metadata=VERIFIED_TEMPLATES[identity]))
    return tuple(rows)


class LauncherService:
    def __init__(self, root=ROOT, save=None, client=CLIENT):
        self.root = Path(root)
        self.config = ServerConfig.load(ROOT/'config/server.toml')
        self.save = Path(save) if save is not None else self.config.state_file
        self.client = Path(client)
        user_root=Path(os.environ['ELS_LOCAL_USER_ROOT']) if self.root==ROOT and os.environ.get('ELS_LOCAL_USER_ROOT') else self.root
        self.home = user_root/'state/launcher'
        self.backups = self.home/'backups'
        self.home.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.repo_lock = threading.RLock()
        self.process = None
        self.phase = 'idle'
        self.message = '准备就绪'
        self.run_dir = None
        self.started_at = None
        self.last_exit = None
        self.check_result = None
        self.worker = None

    def connect(self):
        if not self.save.is_file():
            raise ValueError('尚无存档。请先启动一次游戏以创建本地存档。')
        return sqlite3.connect(self.save.as_uri()+'?mode=ro', uri=True, timeout=3)

    def leased(self):
        try:
            with SaveLease(self.save):
                return False
        except RuntimeError:
            return True

    def state(self):
        with self.lock:
            owned = self.process is not None and self.process.poll() is None
            running = bool(games())
            busy = self.phase in ('checking', 'starting', 'stopping') or owned
            locked = running or busy or self.leased()
            count = 0
            if self.save.is_file():
                with closing(self.connect()) as db:
                    if self.table(db, 'characters'):
                        count = db.execute('SELECT COUNT(*) FROM characters').fetchone()[0]
            return dict(phase=self.phase, message=self.message, game_running=running,
                        owned=owned, gm_locked=locked, save_exists=self.save.is_file(),
                        save=str(self.save), client=str(self.client), character_count=count,
                        last_exit=self.last_exit, started_at=self.started_at,
                        check=self.check_result, run_dir=str(self.run_dir) if self.run_dir else None)

    @staticmethod
    def table(db, name):
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

    def characters(self):
        if not self.save.exists():
            return []
        from els_server.game_data import client_data
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            if not self.table(db, 'characters'):
                return []
            rows = []
            for r in db.execute('''SELECT c.*,COALESCE(b.ed,0) ed,COALESCE(b.experience,0) experience,
                        COALESCE(b.revision,0) balance_revision FROM characters c
                        LEFT JOIN reward_balances b ON c.uid=b.uid ORDER BY c.uid'''):
                row = dict(r)
                row['role'] = ROLE_NAMES[row['unit_type']]
                unit = client_data().unit(row['unit_class'])
                name = unit.get('m_Name') or unit.get('name')
                row['class_name'] = name if isinstance(name, str) else row['role']
                row['item_count'] = db.execute('SELECT COUNT(*) FROM inventory_items WHERE owner=?', (row['uid'],)).fetchone()[0] if self.table(db, 'inventory_items') else 0
                row['town'] = db.execute('SELECT town FROM location WHERE uid=?', (row['uid'],)).fetchone()[0]
                row['version'] = self.version(db, row['uid'])
                from els_server.storage.tutorial_recovery import optional_descriptor
                row['tutorial_recovery'] = optional_descriptor(db, row['uid'], 1)
                rows.append(row)
            return rows

    def version(self, db, uid):
        # Fingerprint every character-owned record touched here, including all
        # inventory rows; a stale browser form cannot silently overwrite a save.
        facts = []
        for table, key in [('characters','uid'),('reward_balances','uid'),('location','uid'),
                           ('inventory_items','owner'),('skill_slots','uid')]:
            if self.table(db, table):
                facts.append([table, [list(r) for r in db.execute(f'SELECT * FROM {table} WHERE {key}=? ORDER BY 1', (uid,))]])
        return hashlib.sha256(repr(facts).encode()).hexdigest()

    def inventory(self, uid):
        bounded_int(uid, 1001, 2**53-1, '角色编号')
        with closing(self.connect()) as db:
            if not db.execute('SELECT 1 FROM characters WHERE uid=?', (uid,)).fetchone():
                raise ValueError('角色不存在')
            from els_server.game_data import client_data
            rows = []
            for r in db.execute('SELECT uid,template,count,bag_group,slot FROM inventory_items WHERE owner=? ORDER BY bag_group,slot', (uid,)):
                try:
                    name = client_data().item(r[1])['name']
                except ValueError:
                    name = '未收录道具'
                rows.append(dict(uid=r[0], template=r[1], name=name, count=r[2], bag=BAGS.get(r[3], str(r[3])), slot=r[4]+1))
            return rows

    def search_items(self, query, group='all', offset=0):
        query = str(query).strip().casefold()[:100]
        offset = bounded_int(offset, 0, 100000, '分页位置')
        rows = [r for r in item_catalog() if (not query or query in str(r['id']) or query in r['name'].casefold())
                and (group == 'all' or str(r['group']) == group)]
        return dict(total=len(rows), rows=rows[offset:offset+40], offset=offset)

    def _backup(self, label, *, tutorial_ticket=None):
        if tutorial_ticket is not None:
            from els_server.storage.tutorial_recovery import backup_ticket
            return self.backups/backup_ticket(tutorial_ticket)
        self.backups.mkdir(parents=True, exist_ok=True)
        name = datetime.now(TZ).strftime('%Y%m%d-%H%M%S-%f')+'-'+label+'.sqlite3'
        path = self.backups/name
        with closing(self.connect()) as source, closing(sqlite3.connect(path)) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('备份校验失败，已取消操作')
        return path

    def backup(self):
        with self.lock:
            path = self._backup('manual')
            return dict(name=path.name, path=str(path), message='存档备份完成')

    def backup_list(self):
        if not self.backups.exists():
            return []
        return [dict(name=p.name, size=p.stat().st_size,
                     time=datetime.fromtimestamp(p.stat().st_mtime, TZ).isoformat(timespec='seconds'))
                for p in sorted(self.backups.glob('*.sqlite3'), reverse=True)[:80]]

    def history(self):
        if not self.save.exists():
            return []
        with closing(self.connect()) as db:
            if not self.table(db, 'launcher_gm_operations'):
                return []
            return [json.loads(r[0]) for r in db.execute('SELECT receipt FROM launcher_gm_operations ORDER BY rowid DESC LIMIT 80')]

    def _tutorial_start(self, data):
        from els_server.storage import tutorial_recovery as recovery
        value=data['value'];uid=data['uid'];operation_id=data['operation_id']
        if not isinstance(value,dict) or set(value)!={'version'}:raise ValueError('请刷新角色资料后重新选择恢复起点')
        recovery.validate_request(uid,value['version'],operation_id,1)
        if not isinstance(data['version'],str) or not re.fullmatch('[0-9a-f]{64}',data['version']):raise ValueError('请刷新角色资料后重试')
        digest=hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        def offline():
            if games() or self.phase in ('checking','starting','stopping') or self.process and self.process.poll() is None:
                raise ValueError('请先正常退出游戏，恢复将在离线后解锁')
        def replay(db):
            recovery.owned(db,uid,1)
            if not self.table(db,'launcher_gm_operations'):return None
            old=db.execute('SELECT request_hash,receipt FROM launcher_gm_operations WHERE operation_id=?',(operation_id,)).fetchone()
            if old is None:return None
            if old[0]!=digest:raise ValueError('操作编号冲突')
            receipt=json.loads(old[1])
            if receipt['uid']!=uid or receipt['action']!='tutorial_start':raise ValueError('操作编号冲突')
            return recovery.bounded_json(dict(receipt,current_town=recovery.location(db,uid)['town']))
        try:
            with self.lock:
                offline()
                with SaveLease(self.save):
                    with closing(self.connect()) as db:
                        db.execute('BEGIN');old=replay(db)
                        if old is not None:return old
                        if self.version(db,uid)!=data['version']:raise recovery.RecoveryError('recovery_stale')
                    stop=threading.Event()
                    ticket=recovery.prepare(self.save,1,uid,value['version'],operation_id,None,stop,backups_path=self.backups)
                    if isinstance(ticket,dict):raise recovery.RecoveryError('recovery_conflict')
                    # All inspection connections are closed before this copy.
                    backup=self._backup('before-tutorial-start',tutorial_ticket=ticket)
                    with closing(sqlite3.connect(self.save,timeout=.25)) as db,db:
                        db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA busy_timeout=250');db.execute('BEGIN IMMEDIATE');offline()
                        old=replay(db)
                        if old is not None:return old
                        descriptor,oldloc=recovery.inspect(db,uid,1)
                        if self.version(db,uid)!=data['version'] or descriptor['version']!=value['version'] or tuple(oldloc[k] for k in recovery.LOCATION)!=ticket.original_location:
                            raise recovery.RecoveryError('recovery_stale')
                        receipt=dict(operation_id=operation_id,uid=uid,time=timestamp(),action='tutorial_start',
                                     detail='恢复'+ROLE_NAMES[descriptor['unit_type']]+'新手起点',backup=backup.name,message='操作完成，下次正常登录生效',
                                     before_location=oldloc,target_town=descriptor['target_town'],current_town=descriptor['target_town'])
                        recovery.bounded_json(receipt)
                        recovery.apply_location(db,uid,descriptor['target_town'],oldloc)
                        db.execute('CREATE TABLE IF NOT EXISTS launcher_gm_operations (operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,receipt TEXT NOT NULL)')
                        db.execute('INSERT INTO launcher_gm_operations VALUES (?,?,?)',(operation_id,digest,json.dumps(receipt,ensure_ascii=False)))
                        offline();recovery.bounded_json(receipt)
                        return receipt
        except RuntimeError as error:raise ValueError('存档正被服务端占用，请先正常退出游戏') from error
        except recovery.RecoveryError as error:
            message={'recovery_stale':'角色数据已变化，请刷新后重新确认','recovery_backup_failed':'存档备份未能完成，角色位置未修改','recovery_conflict':'操作编号冲突，请刷新角色列表'}.get(str(error),'此角色不满足恢复新手起点的条件')
            raise ValueError(message) from error

    def mutate(self, data):
        if not isinstance(data, dict) or set(data) != {'operation_id','uid','version','action','value'}:
            raise ValueError('操作参数不完整，请刷新后重试')
        operation_id = data['operation_id']
        if not isinstance(operation_id, str) or str(uuid.UUID(operation_id)) != operation_id:
            raise ValueError('无效操作编号')
        uid = bounded_int(data['uid'], 1001, 2**53-1, '角色编号')
        action, value = data['action'], data['value']
        if action == 'tutorial_start':return self._tutorial_start(data)
        if action not in ('ed', 'level', 'item', 'town'):
            raise ValueError('尚未开放此项 GM 操作')
        digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        with self.lock:
            if games() or self.phase in ('checking','starting','stopping') or self.process and self.process.poll() is None:
                raise ValueError('请先正常退出游戏，GM 修改将在离线后解锁')
            try:
                with SaveLease(self.save):
                    with closing(sqlite3.connect(self.save, timeout=5)) as db:
                        db.execute('PRAGMA foreign_keys=ON')
                        db.execute('BEGIN IMMEDIATE')
                        try:
                            if self.table(db, 'launcher_gm_operations'):
                                old = db.execute('SELECT request_hash,receipt FROM launcher_gm_operations WHERE operation_id=?', (operation_id,)).fetchone()
                                if old:
                                    if old[0] != digest:
                                        raise ValueError('操作编号冲突')
                                    return json.loads(old[1])
                            if not db.execute('SELECT 1 FROM characters WHERE uid=?', (uid,)).fetchone():
                                raise ValueError('角色不存在')
                            if self.version(db, uid) != data['version']:
                                raise ValueError('角色数据已变化。请刷新角色资料后重新提交。')
                            # Validation precedes backup and state writes.
                            if action == 'ed':
                                bounded_int(value, 1, 2_000_000_000, '发放 ED')
                                old_ed = db.execute('SELECT ed FROM reward_balances WHERE uid=?', (uid,)).fetchone()[0]
                                if old_ed + value > 2**63-1:
                                    raise ValueError('ED 总量超出存档范围')
                            elif action == 'level':
                                bounded_int(value, 1, 99, '等级')
                                old_level = db.execute('SELECT level FROM characters WHERE uid=?', (uid,)).fetchone()[0]
                                if value < old_level:
                                    raise ValueError('仅支持提升等级，避免使现有转职和技能失效')
                                if value == old_level:
                                    raise ValueError('目标等级与当前等级相同')
                            elif action == 'item':
                                if not isinstance(value, dict) or set(value) != {'template','quantity'}:
                                    raise ValueError('请选择道具及数量')
                                bounded_int(value['template'], 1, 2**31-1, '道具编号')
                                bounded_int(value['quantity'], 1, 99, '道具数量')
                                item = next((r for r in item_catalog() if r['id'] == value['template']), None)
                                if item is None:
                                    raise ValueError('该道具尚未在当前服务端验证，不能发放')
                            elif value != 20000:
                                raise ValueError('目前仅开放已验证的魔奇回城位置')
                            backup = self._backup('before-'+action)
                            if action == 'ed':
                                db.execute('UPDATE reward_balances SET ed=ed+?,revision=revision+1 WHERE uid=?', (value, uid))
                                detail = f'发放 {value:,} ED'
                            elif action == 'level':
                                from els_server.game_data import client_data
                                exp = client_data().thresholds[value-1]
                                db.execute('UPDATE characters SET level=?,revision=revision+1 WHERE uid=?', (value, uid))
                                db.execute('UPDATE reward_balances SET experience=?,revision=revision+1 WHERE uid=?', (exp, uid))
                                r = db.execute('SELECT unit_class,level,transcendence,master FROM characters WHERE uid=?', (uid,)).fetchone()
                                character = dict(zip(('unit_class','level','transcendence','master'), r))
                                from els_server.storage.skill_expansion import is_expanded
                                character['skill_row_expanded'] = is_expanded(db, uid)
                                slots = db.execute('SELECT payload FROM skill_slots WHERE uid=?', (uid,)).fetchone()
                                if slots:
                                    import struct
                                    from els_server.domain.skill_rules import upgraded_slots
                                    payload = struct.pack('>22i', *upgraded_slots(struct.unpack('>22i', slots[0]), character))
                                    db.execute('UPDATE skill_slots SET payload=?,revision=revision+1 WHERE uid=?', (payload, uid))
                                detail = f'等级 {old_level} → {value}，经验同步到原生等级阈值'
                            elif action == 'item':
                                from els_server.storage.inventory_state import ensure_inventory, grant_items
                                ensure_inventory(db)
                                grant_items(db, [dict(template=item['id'], metadata=item['metadata'], group=item['group'], quantity=value['quantity'])], uid)
                                detail = f'发放 {item["name"]} × {value["quantity"]}'
                            else:
                                db.execute('UPDATE location SET town=20000,board=0,progress=0,x=0,y=0,z=0,revision=revision+1 WHERE uid=?', (uid,))
                                detail = '回到魔奇初始位置'
                            receipt = dict(operation_id=operation_id, uid=uid, time=timestamp(), action=action,
                                           detail=detail, backup=backup.name, message='操作完成，下次登录生效')
                            db.execute('''CREATE TABLE IF NOT EXISTS launcher_gm_operations (
                                operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,receipt TEXT NOT NULL)''')
                            db.execute('INSERT INTO launcher_gm_operations VALUES (?,?,?)',
                                       (operation_id, digest, json.dumps(receipt, ensure_ascii=False)))
                            db.commit()
                            return receipt
                        except BaseException:
                            db.rollback()
                            raise
            except RuntimeError as e:
                raise ValueError('存档正被服务端占用，请先正常退出游戏') from e

    def check(self):
        with self.lock:
            if self.phase in ('checking','starting','stopping'):
                raise ValueError('正在处理上一项任务，请稍候')
            self.phase = 'checking'; self.message = '正在检查客户端、资源和存档…'
            self.worker = threading.Thread(target=self._check_worker, daemon=True)
            self.worker.start()
        return dict(message='已开始检查')

    def _check_worker(self):
        results = []
        try:
            from els_server.game_data import CLIENT_SHA, client_data
            if not self.client.is_file():
                raise ValueError('找不到客户端：'+str(self.client))
            with self.client.open('rb') as f:
                ok = hashlib.file_digest(f, 'sha256').hexdigest() == CLIENT_SHA
            results.append(dict(name='客户端版本', ok=ok, detail='已验证 DX11 构建' if ok else '客户端版本不匹配'))
            if not ok:
                raise ValueError('客户端版本不匹配，停止检查')
            from tools.dx11_resource_compat import resource_compat_source
            from tools.local_resource_index_compat import source
            image = (ROOT/'analysis/client-6c6b5180/native-prefixes.bin').read_bytes()
            resource_compat_source(image, self.client.parent)
            source(image, self.client.parent)
            results.append(dict(name='启动资源兼容', ok=True, detail='两个固定资源包与目录校验通过'))
            client_data()
            results.append(dict(name='服务端配表', ok=True, detail='配表哈希与版本通过'))
            if self.save.exists():
                with closing(self.connect()) as db:
                    good = db.execute('PRAGMA quick_check').fetchone() == ('ok',)
                results.append(dict(name='存档完整性', ok=good, detail='SQLite 检查通过' if good else '存档检查失败'))
            else:
                results.append(dict(name='存档', ok=True, detail='首次启动时创建独立空白开发存档'))
            self.message = '检查完成，可以启动游戏' if all(r['ok'] for r in results) else '检查未通过，请查看结果'
        except Exception as e:
            results.append(dict(name='检查结果', ok=False, detail=str(e)))
            self.message = '检查未通过，请查看结果'
        finally:
            with self.lock:
                self.check_result = dict(time=timestamp(), rows=results)
                self.phase = 'idle'

    def start(self):
        with self.lock:
            if self.save != self.config.state_file or self.client != CLIENT:
                raise ValueError('验证环境不允许启动正式游戏')
            if self.phase in ('checking','starting','stopping') or self.process and self.process.poll() is None:
                raise ValueError('启动任务正在运行')
            if games() or self.leased():
                raise ValueError('游戏或服务端已经运行，请先正常退出已有实例')
            # Existing launcher performs complete pinned resource checks before
            # client spawn; this UI never invents or bypasses a new launch path.
            self.phase = 'starting'; self.message = '正在校验资源并启动本地服务…'
            self.run_dir = None; self.started_at = timestamp()
            self.worker = threading.Thread(target=self._launch_worker, daemon=True)
            self.worker.start()
            return dict(message='启动中，请稍候')

    def _launch_worker(self):
        log_path = self.home/'launch.log'
        try:
            python = Path(sys.executable).with_name('python.exe') if os.name == 'nt' else Path(sys.executable)
            with log_path.open('w', encoding='utf8') as log:
                with self.lock:
                    self.process = subprocess.Popen([str(python), str(ROOT/'tools/launch_integrated_local.py')],
                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                        env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1'))
                while self.process.poll() is None:
                    # Only accept a directory printed by our verified child and
                    # verify its client process identity before allowing stop.
                    content = log_path.read_text(encoding='utf8', errors='replace')
                    for line in content.splitlines():
                        candidate = Path(line.strip())
                        if candidate.is_absolute() and candidate.is_relative_to(ROOT/'analysis/client-6c6b5180') and (candidate/'client-process.json').is_file():
                            self.run_dir = candidate
                    if self.run_dir and games() and self.phase != 'stopping':
                        self.phase = 'running'; self.message = '游戏运行中 · GM 修改已锁定'
                    time.sleep(.7)
                code = self.process.returncode
            with self.lock:
                self.last_exit = code
                self.message = '游戏已退出，存档已交回 GM 工具' if code == 0 else '启动任务已结束，请查看运行日志'
        except Exception as e:
            self.message = '启动失败：'+str(e)
            self.last_exit = -1
        finally:
            self.phase = 'idle'

    def stop(self):
        with self.lock:
            if not self.process or self.process.poll() is not None or not self.run_dir:
                raise ValueError('没有可停止的本启动器游戏实例，请在游戏内正常退出')
            identity = json.loads((self.run_dir/'client-process.json').read_text(encoding='utf8'))
            p = psutil.Process(identity['pid'])
            if abs(p.create_time()-identity['created']) > .001 or Path(p.exe()).resolve() != self.client.resolve():
                raise ValueError('游戏进程身份已变化，请在游戏内退出')
            (self.run_dir/'client.stop').write_text('launcher requested owned shutdown', encoding='utf8')
            self.phase = 'stopping'; self.message = '正在结束本次游戏并等待服务端保存…'
            return dict(message='正在退出游戏')

    def logs(self):
        path = self.home/'launch.log'
        if not path.exists():
            return '暂无启动日志。启动游戏后，可在这里查看检查结果。'
        with path.open('rb') as f:
            f.seek(max(0, path.stat().st_size-20000)); content = f.read().decode('utf8', 'replace')
        content = re.sub(r'pxk19\w+', '[启动参数已隐藏]', content)
        return content[-16000:]

    # ---------- repository ----------
    def _git_exe(self):
        """Find Git even when the launcher was started outside a shell with Git on PATH."""
        candidates = []
        recorded = self.home/'git-path.txt'
        try:
            if recorded.is_file():
                candidates.append(Path(recorded.read_text(encoding='utf8').strip()))
        except OSError:
            pass
        found = shutil.which('git')
        if found:
            candidates.append(Path(found))
        home = Path.home()
        local = Path(os.environ.get('LOCALAPPDATA', ''))
        candidates += [
            Path(os.environ.get('ProgramFiles', r'C:\Program Files'))/'Git/cmd/git.exe',
            Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))/'Git/cmd/git.exe',
            local/'Programs/Git/cmd/git.exe',
            home/'.qoder-cn/bin/git/cmd/git.exe',
            home/'.qoder-cn/bin/git/mingw64/bin/git.exe',
            local/'Programs/WorkBuddy/resources/vendor/PortableGit/cmd/git.exe',
        ]
        for path in candidates:
            try:
                if path.is_file():
                    return str(path)
            except OSError:
                continue
        raise ValueError('找不到 Git。请安装 Git for Windows，或把 git.exe 路径写入 '+str(recorded)+' 后重试。')

    def _git(self, *args, timeout=60):
        return subprocess.run(
            [self._git_exe(), '-c', 'core.quotepath=false', *args], cwd=str(self.root),
            capture_output=True, text=True, encoding='utf8', errors='replace',
            timeout=timeout, env=dict(os.environ, GIT_TERMINAL_PROMPT='0'),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    @staticmethod
    def _git_detail(result):
        return ((result.stderr or '') + '\n' + (result.stdout or '')).strip()

    def _game_busy(self):
        return (self.phase in ('checking', 'starting', 'stopping') or bool(games())
                or bool(self.process and self.process.poll() is None) or self.leased())

    def _repo_fetch(self):
        fetch = self._git('fetch', '--no-tags', 'origin',
                          'refs/heads/main:refs/remotes/origin/main', timeout=90)
        if fetch.returncode != 0:
            raise ValueError('无法刷新远端状态：'+self._git_detail(fetch)[:600])

    @staticmethod
    def _review_branch(branch):
        return branch.startswith(('fix/', 'feature/', 'sync/'))

    @staticmethod
    def _review_url(remote, branch):
        match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?', remote)
        if not match or not LauncherService._review_branch(branch):
            return None
        return 'https://github.com/'+match.group(1)+'/compare/main...'+quote(branch, safe='')+'?expand=1'

    def repo_state(self, *, refresh=False):
        if not (self.root/'.git').exists():
            raise ValueError('当前目录不是 Git 仓库')
        with self.repo_lock:
            if refresh:
                self._repo_fetch()
            head = self._git('log', '-1', '--format=%h|%ad|%s', '--date=format:%Y-%m-%d %H:%M', timeout=15)
            parts = (head.stdout.strip() or '||').split('|', 2)
            branch = self._git('rev-parse', '--abbrev-ref', 'HEAD', timeout=15).stdout.strip()
            status = self._git('status', '--porcelain', timeout=20).stdout
            changed = [dict(status=line[:2].strip() or 'M', path=line[3:])
                       for line in status.splitlines() if len(line) > 3]
            remote = ''
            behind = ahead = 0
            if self._git('rev-parse', '--verify', '--quiet', 'origin/main', timeout=15).returncode == 0:
                remote = self._git('config', '--get', 'remote.origin.url', timeout=10).stdout.strip()
                behind = int(self._git('rev-list', '--count', 'HEAD..origin/main', timeout=15).stdout.strip() or 0)
                ahead = int(self._git('rev-list', '--count', 'origin/main..HEAD', timeout=15).stdout.strip() or 0)
            name = self._git('config', '--get', 'user.name', timeout=10).stdout.strip()
            email = self._git('config', '--get', 'user.email', timeout=10).stdout.strip()
            owner = re.search(r'github\.com[:/]([^/]+)/', remote or '')
            owner = owner.group(1) if owner else ''
            return dict(repo=str(self.root), branch=branch, head=parts[0],
                        when=parts[1] if len(parts) > 2 else '',
                        subject=parts[2] if len(parts) > 2 else '',
                        changed=changed, dirty=bool(changed), remote=remote,
                        behind=behind, ahead=ahead,
                        remote_checked=refresh,
                        review_url=self._review_url(remote, branch),
                        identity=dict(name=name, email=email, configured=bool(name and email),
                                      suggest_name=owner,
                                      suggest_email=owner+'@users.noreply.github.com' if owner else ''),
                        git=self._git_exe(),
                        game_running=self._game_busy(),
                        can_pull=not changed and behind > 0 and ahead == 0 and branch == 'main' and not self._game_busy())

    def repo_commit(self, data):
        if not isinstance(data, dict):
            raise ValueError('无效请求')
        message = str(data.get('message') or '').strip()
        name = str(data.get('name') or '').strip()
        email = str(data.get('email') or '').strip()
        if len(message) > 200:
            raise ValueError('提交说明最多 200 个字符')
        with self.lock, self.repo_lock:
            if self._game_busy():
                raise ValueError('请先正常退出游戏和服务端，再提交代码')
            state = self.repo_state()
            branch = state['branch']
            if branch != 'main' and not self._review_branch(branch):
                raise ValueError('请使用 main、fix/、feature/ 或 sync/ 分支；不能推送快照或分离的 HEAD')
            if name or email:
                if not name or '@' not in email:
                    raise ValueError('请同时填写有效的提交人名称与邮箱')
                for key, value in (('user.name', name), ('user.email', email)):
                    configured = self._git('config', '--local', key, value, timeout=10)
                    if configured.returncode != 0:
                        raise ValueError('保存 Git 身份失败：'+self._git_detail(configured)[:600])
            elif not state['identity']['configured']:
                raise ValueError('尚未配置 Git 提交身份，请填写提交人名称与邮箱')
            if not state['dirty'] and state['ahead'] == 0:
                raise ValueError('没有可提交的改动')
            if state['dirty'] and not message:
                raise ValueError('请填写提交说明')
            # Never write origin/main or rewrite published commits. A failed
            # push leaves this same review branch available for a safe retry.
            if branch == 'main':
                branch = 'fix/local-'+uuid.uuid4().hex[:12]
                switched = self._git('switch', '-c', branch, timeout=30)
                if switched.returncode != 0:
                    raise ValueError('创建修复分支失败：'+self._git_detail(switched)[:600])
            add = self._git('add', '-A', timeout=60)
            if add.returncode != 0:
                raise ValueError('暂存改动失败：'+self._git_detail(add)[:600])
            staged = self._git('diff', '--cached', '--quiet', timeout=30).returncode != 0
            if not staged and state['ahead'] == 0:
                raise ValueError('没有可提交的改动')
            notes = []
            if staged:
                if not message:
                    raise ValueError('请填写提交说明')
                commit = self._git('commit', '-m', message, timeout=120)
                if commit.returncode != 0:
                    raise ValueError('提交失败：'+self._git_detail(commit)[:600])
                notes.append('已创建本地提交')
            push = self._git('push', '--set-upstream', 'origin',
                             'HEAD:refs/heads/'+branch, timeout=180)
            if push.returncode != 0:
                raise ValueError(('已提交到本地，但推送失败：' if notes else '推送失败：')+self._git_detail(push)[:600])
            notes.append('已推送修复分支 '+branch+'；请提交 PR，由维护者审查合并')
            head = self._git('log', '-1', '--format=%h %s', timeout=10).stdout.strip()
            return dict(message='；'.join(notes), head=head, branch=branch,
                        review_url=self._review_url(state['remote'], branch))

    def repo_pull(self):
        with self.lock, self.repo_lock:
            if self._game_busy():
                raise ValueError('请先正常退出游戏和服务端，再拉取代码')
            state = self.repo_state()
            if state['branch'] != 'main':
                raise ValueError('当前不在 main 分支，请先切回 main')
            if state['dirty']:
                raise ValueError('工作区有未提交改动，请先在「提交到仓库」中提交')
            before = self._runtime_sha()
            self._repo_fetch()
            behind = int(self._git('rev-list', '--count', 'HEAD..origin/main', timeout=15).stdout.strip() or 0)
            ahead = int(self._git('rev-list', '--count', 'origin/main..HEAD', timeout=15).stdout.strip() or 0)
            if behind == 0:
                return dict(message='已是最新版本'+(f'，本地有 {ahead} 个提交未推送' if ahead else ''))
            if ahead == 0:
                merge = self._git('merge', '--ff-only', 'origin/main', timeout=120)
                if merge.returncode != 0:
                    raise ValueError('快进失败：'+self._git_detail(merge)[:600])
                notes = [f'已快进 {behind} 个提交']
            else:
                raise ValueError(f'远端有 {behind} 个新提交，本地主干有 {ahead} 个提交；请先推送修复分支并经 PR 审查，不能自动改写主干历史')
            head = self._git('log', '-1', '--format=%h %s', timeout=10).stdout.strip()
            if self._runtime_sha() != before:
                notes.append('运行资源包有变化，请关闭启动器后打开「更新单机版」完成同步')
            return dict(message='；'.join(notes), head=head)

    def _runtime_sha(self):
        try:
            return json.loads((self.root/'runtime-assets.lock.json').read_text(encoding='utf8')).get('archive_sha256', '')
        except Exception:
            return ''

    def features(self):
        document = json.loads((ROOT/'config/integration_roadmap.json').read_text(encoding='utf8'))
        return [dict(id=f['id'], title=f['title'], status=f['status'], current=f['current'], missing=f.get('next_or_missing','')) for f in document['features']]

    def open_folder(self, which):
        paths = {'save':self.save.parent, 'backups':self.backups,
                 'logs':self.run_dir or self.home, 'client':self.client.parent}
        if which not in paths:
            raise ValueError('未知目录')
        path = paths[which]; path.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            os.startfile(path)
        return dict(message='已打开目录')
