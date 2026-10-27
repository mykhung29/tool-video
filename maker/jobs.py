"""Batch render queue: one worker thread processes jobs in order.

Each job ends as done/error/cancelled independently, so one failing content never blocks
the rest. Stopping cancels the running job (it goes back to pending) and pauses the queue.
"""
import threading
import time
import traceback
import uuid

from . import render
from .projects import set_status


class Queue:
    def __init__(self):
        self.jobs = []
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.cancel = threading.Event()
        self.paused = False
        self.current = None
        threading.Thread(target=self._loop, daemon=True, name="render-queue").start()

    def add(self, names, preview=False):
        added = []
        with self.lock:
            active = {(j["name"], j["preview"]) for j in self.jobs if j["status"] in ("pending", "running")}
            for n in names:
                if (n, preview) in active:
                    continue
                job = {"id": uuid.uuid4().hex[:10], "name": n, "preview": preview, "status": "pending",
                       "progress": 0.0, "message": "Đang chờ", "error": None, "output": None,
                       "added": time.time(), "started": None, "finished": None}
                self.jobs.append(job)
                added.append(job["id"])
                if not preview:
                    set_status(n, status="queued", error=None)
        self.wake.set()
        return added

    def stop(self):
        with self.lock:
            self.paused = True
            if self.current:
                self.cancel.set()

    def resume(self):
        with self.lock:
            self.paused = False
        self.wake.set()

    def retry_failed(self):
        with self.lock:
            failed = [j for j in self.jobs if j["status"] in ("error", "cancelled")]
            for j in failed:
                j.update(status="pending", progress=0.0, message="Đang chờ", error=None)
                if not j["preview"]:
                    set_status(j["name"], status="queued", error=None)
            self.paused = False
        self.wake.set()
        return len(failed)

    def remove(self, job_id):
        with self.lock:
            for j in self.jobs:
                if j["id"] == job_id:
                    if j["status"] == "running":
                        self.cancel.set()
                        j["remove"] = True
                    else:
                        self.jobs.remove(j)
                        if j["status"] == "pending" and not j["preview"]:
                            set_status(j["name"], status="new")
                    return True
        return False

    def clear_finished(self):
        with self.lock:
            self.jobs = [j for j in self.jobs if j["status"] in ("pending", "running")]

    def snapshot(self):
        with self.lock:
            jobs = [dict(j) for j in self.jobs]
            paused = self.paused
        counts = {}
        for j in jobs:
            counts[j["status"]] = counts.get(j["status"], 0) + 1
        total = len(jobs)
        overall = (sum(1.0 if j["status"] in ("done", "error", "cancelled") else j["progress"] for j in jobs)
                   / total) if total else 0.0
        return {"jobs": jobs, "paused": paused, "counts": counts, "overall": overall,
                "running": any(j["status"] == "running" for j in jobs)}

    def _next(self):
        with self.lock:
            if self.paused:
                return None
            for j in self.jobs:
                if j["status"] == "pending":
                    j.update(status="running", started=time.time(), progress=0.0, message="Bắt đầu")
                    self.current = j
                    self.cancel.clear()
                    return j
        return None

    def _loop(self):
        while True:
            job = self._next()
            if job is None:
                self.wake.wait(1.0)
                self.wake.clear()
                continue
            name = job["name"]
            if not job["preview"]:
                set_status(name, status="rendering", error=None)

            def progress(frac, msg, job=job):
                job["progress"] = frac
                job["message"] = msg

            try:
                res = render.render(name, preview=job["preview"], progress=progress, cancel=self.cancel)
                job.update(status="done", progress=1.0, message="Hoàn thành", output=res["output"])
            except render.Cancelled:
                with self.lock:
                    removed = job.get("remove")
                    job.update(status="pending" if not removed else "cancelled", progress=0.0,
                               message="Đã dừng — sẽ dựng lại khi tiếp tục")
                    if removed and job in self.jobs:
                        self.jobs.remove(job)
                if not job["preview"]:
                    set_status(name, status="queued" if not job.get("remove") else "new")
            except Exception as e:  # report the reason, keep going with the next content
                msg = str(e) or e.__class__.__name__
                traceback.print_exc()
                job.update(status="error", message="Lỗi", error=msg)
                if not job["preview"]:
                    set_status(name, status="error", error=msg)
            finally:
                job["finished"] = time.time()
                with self.lock:
                    self.current = None


QUEUE = None


def get_queue() -> Queue:
    global QUEUE
    if QUEUE is None:
        QUEUE = Queue()
    return QUEUE
