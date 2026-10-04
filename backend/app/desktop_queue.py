"""Durable single-machine queue. No broker service; desktop mode only.

Task payloads live in the per-user protected data directory. Results and errors
never retain payloads. A crashed worker's lease is recoverable; jobs must remain
idempotent just as with the Celery transport.
"""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
import uuid
from contextlib import contextmanager


class DesktopQueue:
    def __init__(self, path=None):
        self.path = Path(path or os.environ["DESKTOP_QUEUE_PATH"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks = {}
        self.conf = SimpleNamespace(beat_schedule={})
        # Celery's configuration object supports update; only shared settings
        # are written by worker.py and unused by this transport.
        self.conf.update = self.configure
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE,
                    name TEXT NOT NULL, payload TEXT NOT NULL,
                    state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    available REAL NOT NULL, lease REAL, owner TEXT,
                    max_retries INTEGER NOT NULL, updated REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS due_jobs ON jobs(state, available);
                CREATE TABLE IF NOT EXISTS health (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), seen REAL NOT NULL
                );
            """)

    def configure(self, **settings):
        for key, value in settings.items():
            setattr(self.conf, key, value)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def task(self, **options):
        def decorate(function):
            task = DesktopTask(self, function, options)
            self.tasks[task.name] = task
            return task

        return decorate

    def enqueue(self, name, args, kwargs, max_retries):
        payload = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
        fingerprint = hashlib.sha256((name + payload).encode()).hexdigest()
        job_id, clock = uuid.uuid4().hex, time.time()
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO jobs VALUES (?, ?, ?, ?, 'queued', 0, ?, NULL, NULL, ?, ?)",
                (job_id, fingerprint, name, payload, clock, max_retries, clock),
            )
            return db.execute(
                "SELECT id FROM jobs WHERE fingerprint=?", (fingerprint,)
            ).fetchone()[0]

    def claim(self, clock=None):
        clock = time.time() if clock is None else clock
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE jobs SET state='queued', owner=NULL, lease=NULL WHERE state='running' AND lease<?",
                (clock,),
            )
            row = db.execute(
                "SELECT * FROM jobs WHERE state='queued' AND available<=? ORDER BY available LIMIT 1",
                (clock,),
            ).fetchone()
            if not row:
                return None
            owner = uuid.uuid4().hex
            db.execute(
                "UPDATE jobs SET state='running', attempts=attempts+1, lease=?, owner=?, updated=? WHERE id=?",
                (clock + 900, owner, clock, row["id"]),
            )
            return dict(row) | {"owner": owner, "attempts": row["attempts"] + 1}

    def finish(self, job, failed=False):
        clock = time.time()
        retry = failed and job["attempts"] <= job["max_retries"]
        with self.connect() as db:
            if retry:
                db.execute(
                    "UPDATE jobs SET state='queued', owner=NULL, lease=NULL, available=?, updated=? WHERE id=? AND owner=?",
                    (
                        clock + min(2 ** job["attempts"], 300),
                        clock,
                        job["id"],
                        job["owner"],
                    ),
                )
            else:
                db.execute(
                    "UPDATE jobs SET state=?, payload='{}', fingerprint=NULL, owner=NULL, lease=NULL, updated=? WHERE id=? AND owner=?",
                    ("failed" if failed else "done", clock, job["id"], job["owner"]),
                )

    def run_one(self):
        job = self.claim()
        if not job:
            return False
        try:
            payload = json.loads(job["payload"])
            self.tasks[job["name"]](*payload["args"], **payload["kwargs"])
        except Exception:
            # Do not write tokens, document contents or exception arguments.
            self.finish(job, failed=True)
        else:
            self.finish(job)
        return True

    def heartbeat(self):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO health VALUES (1, ?)", (time.time(),))
            db.execute(
                "DELETE FROM jobs WHERE state IN ('done','failed') AND updated<?",
                (time.time() - 7 * 86400,),
            )

    def available(self):
        with self.connect() as db:
            row = db.execute("SELECT seen FROM health WHERE singleton=1").fetchone()
            return bool(row and 0 <= time.time() - row[0] < 30)


class DesktopTask:
    def __init__(self, queue, function, options):
        self.queue, self.function = queue, function
        self.name = options["name"]
        self.max_retries = options.get("max_retries", 0)

    def __call__(self, *args, **kwargs):
        return self.function(*args, **kwargs)

    def delay(self, *args, **kwargs):
        return SimpleNamespace(
            id=self.queue.enqueue(self.name, args, kwargs, self.max_retries)
        )


def main():
    import threading
    from .worker import celery_app as queue
    from .desktop_queue import DesktopQueue as QueueType

    if not isinstance(queue, QueueType):
        raise RuntimeError("Desktop worker requires WORKFLOW_DESKTOP=1.")
    stop = threading.Event()

    def pulse():
        while not stop.is_set():
            queue.heartbeat()
            stop.wait(5)

    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    schedules = {name: 0.0 for name in queue.conf.beat_schedule}
    try:
        while True:
            clock = time.monotonic()
            for name, schedule in queue.conf.beat_schedule.items():
                if clock >= schedules[name]:
                    queue.tasks[schedule["task"]].delay()
                    schedules[name] = clock + float(schedule["schedule"])
            if not queue.run_one():
                time.sleep(0.5)
    finally:
        stop.set()
        thread.join(timeout=10)


if __name__ == "__main__":
    main()
