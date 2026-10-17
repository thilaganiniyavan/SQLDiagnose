# jobs.py
# A small in-process job queue for slow work (NL->SQL generation takes tens of seconds on a CPU).
# Jobs run one at a time on a single worker thread: the generator is large, not thread-safe, and
# running two at once on a small machine only makes both slower.

import threading
import time
import uuid
from collections import OrderedDict, deque
from typing import Any, Callable, Deque, Dict, Optional

JOB_TTL_S = 3600          # finished jobs are forgotten after an hour


class QueueFull(Exception):
    pass


class Job:
    def __init__(self, kind: str, owner: Optional[str], fn: Callable[["Job"], Any], meta: Dict[str, Any]):
        self.id = uuid.uuid4().hex
        self.kind, self.owner, self.fn, self.meta = kind, owner, fn, meta
        self.status = "queued"            # queued | running | done | error | cancelled
        self.phase: Optional[str] = None  # free-form progress label while running
        self.result: Any = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error", "cancelled")


class JobQueue:
    def __init__(self, max_pending: int = 20):
        self.max_pending = max_pending
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._pending: Deque[Job] = deque()
        self._cond = threading.Condition()
        self._worker = threading.Thread(target=self._run, name="job-worker", daemon=True)
        self._worker.start()

    def submit(self, kind: str, fn: Callable[[Job], Any], owner: Optional[str] = None, **meta) -> Job:
        with self._cond:
            self._expire()
            if len(self._pending) >= self.max_pending:
                raise QueueFull(f"{len(self._pending)} jobs are already waiting; try again shortly.")
            job = Job(kind, owner, fn, meta)
            self._jobs[job.id] = job
            self._pending.append(job)
            self._cond.notify()
            return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._cond:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        """Cancels a job that has not started yet."""
        with self._cond:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                return False
            self._pending.remove(job)
            job.status, job.finished_at = "cancelled", time.time()
            return True

    def position(self, job: Job) -> int:
        """1-based place in the queue (0 when running or finished)."""
        with self._cond:
            try:
                return self._pending.index(job) + 1
            except ValueError:
                return 0

    def describe(self, job: Job) -> Dict[str, Any]:
        now = job.finished_at or time.time()
        return {"id": job.id, "kind": job.kind, "status": job.status, "phase": job.phase,
                "queue_position": self.position(job), "result": job.result, "error": job.error,
                "created_at": job.created_at, "started_at": job.started_at, "finished_at": job.finished_at,
                "elapsed_s": round(now - (job.started_at or job.created_at), 1), **job.meta}

    def _expire(self):
        cutoff = time.time() - JOB_TTL_S
        for jid in [j.id for j in self._jobs.values() if j.finished and (j.finished_at or 0) < cutoff]:
            del self._jobs[jid]

    def _run(self):
        while True:
            with self._cond:
                while not self._pending:
                    self._cond.wait()
                job = self._pending.popleft()
                job.status, job.started_at = "running", time.time()
            try:
                result = job.fn(job)
                job.result, job.status = result, "done"
            except Exception as e:                      # reported to the client, never raised
                job.error, job.status = str(e) or e.__class__.__name__, "error"
            finally:
                job.finished_at = time.time()
                job.phase = None
