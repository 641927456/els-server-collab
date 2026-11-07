class ProbeClock:

    def __init__(self, label):
        self.label = label
        self.cursor = 0
        self.target = 1
        self._attempt = None
        self.closed = False
        self.identity = label

    def observe(self, session, *, stop=False):
        if self.closed:
            return
        if self.target > self.cursor:
            self._attempt = (self.label, self.target)
            current_commit().persist(self, session.application.clock_writer.path, functools.partial(self.write, end=self.target))
            self.cursor = self.target
        if stop:
            self.closed = True
            self.identity = None

    def write(self, db, *, end):
        db.execute('INSERT INTO own_clock VALUES(?,?)ON CONFLICT(label)DO UPDATE SET ends=excluded.ends', (self.label, end))

class OwnSession:
    pass

def transaction_checks():
    checks = {}
    with tempfile.TemporaryDirectory(prefix='own-async-clock-', dir=bootstrap.HERE) as raw:
        path = Path(raw) / 'clocks.sqlite3'
        with contextlib.closing(sqlite3.connect(path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE own_clock(label TEXT PRIMARY KEY,ends INTEGER)')
            db.commit()
        writer = ClockWriter(path)
        writer.prepare()
        session = OwnSession()
        session.application = SimpleNamespace(clock_writer=writer)
        a, b = (ProbeClock('attendance'), ProbeClock('title'))
        pair = PairClocks(a, b)

        def cold():
            with contextlib.closing(sqlite3.connect(path)) as db:
                return db.execute('SELECT label,ends FROM own_clock ORDER BY label').fetchall()
        original = writer_module.commit_write
        entered = threading.Event()
        release = threading.Event()
        done = threading.Event()
        errors = []

        def held(db):
            entered.set()
            assert release.wait(3), 'Owned commit barrier exceeded'
            return original(db)

        def critical():
            try:
                pair.observe(session)
            except BaseException as error:
                errors.append(repr(error))
            finally:
                done.set()
        try:
            with patch.object(writer_module, 'commit_write', held):
                pair.observe_background(session)
                assert entered.wait(2)
                pending = pair.pending
                assert pending is not None and (not pending.future.done())
                assert (a.cursor, b.cursor) == (0, 0) and cold() == []
                pair.observe_background(session)
                assert pair.pending is pending and writer.jobs == 1
                checks['background_returns_with_one_pending_job_and_only_durable_cursors_visible'] = True
                thread = threading.Thread(target=critical)
                thread.start()
                assert not done.wait(0.05)
                release.set()
                assert done.wait(2)
                thread.join()
                assert not errors
            assert cold() == [('attendance', 1), ('title', 1)] and (a.cursor, b.cursor) == (1, 1)
            checks['critical_observation_waits_for_FULL_commit_before_advancing_cursors'] = True
            a.target = b.target = 2

            def failed(db):
                error = sqlite3.OperationalError('owned physical commit failure')
                error.sqlite_errorcode = sqlite3.SQLITE_IOERR
                raise error
            with patch.object(writer_module, 'commit_write', failed):
                pair.observe_background(session)
                pending = pair.pending
                assert pending is not None
                pending.future.result(timeout=2)
                try:
                    pair.observe_background(session)
                except sqlite3.OperationalError as error:
                    assert error.sqlite_errorcode == sqlite3.SQLITE_IOERR
                else:
                    raise AssertionError('Original I/O error must propagate')
            assert cold() == [('attendance', 1), ('title', 1)] and (a.cursor, b.cursor) == (1, 1) and (pair.pending is None)
            pair.observe(session)
            assert cold() == [('attendance', 2), ('title', 2)]
            pair.observe(session)
            assert cold() == [('attendance', 2), ('title', 2)]
            checks['failed_commit_rolls_back_both_cursors_and_original_interval_can_commit_once'] = True
            a.target = b.target = 3
            entered.clear()
            release.clear()
            done.clear()
            errors.clear()
            with patch.object(writer_module, 'commit_write', held):
                pair.observe_background(session)
                assert entered.wait(2)

                def stop():
                    try:
                        pair.observe(session, stop=True)
                    except BaseException as error:
                        errors.append(repr(error))
                    finally:
                        done.set()
                thread = threading.Thread(target=stop)
                thread.start()
                assert not done.wait(0.05)
                release.set()
                assert done.wait(2)
                thread.join()
                assert not errors
            assert a.closed and b.closed and (pair.pending is None) and (pair.session_ref is None)
            assert cold() == [('attendance', 3), ('title', 3)]
            checks['disconnect_drains_pending_commit_and_closes_both_clocks'] = True
        finally:
            release.set()
            writer.close()
    assert not Path(raw).exists()
    return checks

class Cases(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='own-clock-failures-', dir=bootstrap.HERE)
        self.path = Path(self.tmp.name) / 'own.sqlite3'
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE own_clock(label TEXT PRIMARY KEY,ends INTEGER)')
            db.commit()
        self.writer = ClockWriter(self.path)
        self.writer.prepare()
        self.session = OwnSession()
        self.session.application = SimpleNamespace(clock_writer=self.writer)
        self.a, self.b = (ProbeClock('attendance'), ProbeClock('title'))
        self.pair = PairClocks(self.a, self.b)

    def tearDown(self):
        self.writer.close()
        self.tmp.cleanup()
        self.assertFalse(Path(self.tmp.name).exists())

    def cold(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT label,ends FROM own_clock ORDER BY label').fetchall()

    def test_busy_background_keeps_cursors_and_interval(self):
        entered = threading.Event()
        release = threading.Event()
        original = module.commit_write

        def held(db):
            entered.set()
            assert release.wait(2)
            return original(db)
        try:
            with patch.object(module, 'commit_write', held):
                first = self.writer.submit(((self.path, lambda db: db.execute('SELECT 1')),), stop=False, background=True)
                self.assertTrue(entered.wait(1))
                self.pair.observe_background(self.session)
                pending = self.pair.pending
                self.assertTrue(pending.future.done())
                finish_observation(pending)
                self.pair.pending = None
                self.assertEqual((self.a.cursor, self.b.cursor), (0, 0))
                self.assertEqual(self.a._deferred, ('attendance', 1))
                self.assertEqual(self.cold(), [])
                release.set()
                first.result(timeout=1)
        finally:
            release.set()
        self.pair.observe(self.session)
        self.assertEqual(self.cold(), [('attendance', 1), ('title', 1)])

    def test_failed_pending_stop_reports_error_and_still_flushes_and_closes(self):
        original = module.commit_write
        calls = []

        def fail_once(db):
            calls.append(True)
            if len(calls) == 1:
                error = sqlite3.OperationalError('owned first commit I/O failure')
                error.sqlite_errorcode = sqlite3.SQLITE_IOERR
                raise error
            return original(db)
        with patch.object(module, 'commit_write', fail_once):
            self.pair.observe_background(self.session)
            self.pair.pending.future.result(timeout=1)
            with self.assertRaisesRegex(sqlite3.OperationalError, 'owned first commit I/O failure'):
                self.pair.observe(self.session, stop=True)
        self.assertTrue(self.a.closed and self.b.closed)
        self.assertIsNone(self.pair.pending)
        self.assertIsNone(self.pair.session_ref)
        self.assertEqual(self.cold(), [('attendance', 1), ('title', 1)])
        self.assertEqual(len(calls), 2)

    def test_only_background_jobs_detach_caller_context(self):
        marker = ContextVar('owned_clock_sample', default='detached')
        seen = []
        token = marker.set('live-worker')
        try:

            def write(db):
                seen.append(marker.get())
            self.writer.submit(((self.path, write),), stop=False, background=True).result(timeout=1)
            self.writer.commit(((self.path, write),), stop=False)
        finally:
            marker.reset(token)
        self.assertEqual(seen, ['detached', 'live-worker'])

    def test_cursors_are_restored_before_writer_publication(self):
        original = self.writer.submit
        published = []

        def submit(*args, **kwargs):
            self.assertEqual((self.a.cursor, self.b.cursor), (0, 0))
            self.assertEqual((self.a.label, self.b.label), ('attendance', 'title'))
            published.append(True)
            return original(*args, **kwargs)
        with patch.object(self.writer, 'submit', submit):
            self.pair.observe_background(self.session)
        self.pair.pending.future.result(timeout=1)
        finish_observation(self.pair.pending)
        self.pair.pending = None
        self.assertEqual(published, [True])
        self.assertEqual((self.a.cursor, self.b.cursor), (1, 1))
