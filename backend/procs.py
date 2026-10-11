"""
Worker processes, and how they are killed.

Targets run in parallel, one process each (backend/worker.py), not one thread
each, for three reasons found the hard way:

- **A stuck page has to be killable on its own.** Every Playwright call on a
  page that stops answering waits forever, and the sync API cannot be
  cancelled from another thread. The old guard killed every Chromium the
  server owned — fine one at a time, and with ten running it takes nine
  healthy pages down with the stuck one.
- **Analysis is CPU-bound Python.** Parsing a 40-60 MB HAR holds the GIL; in
  a thread it stalls beacon delivery and the 0.15s overlay polling of every
  other session in the process.
- **Playwright's sync API is bound to the thread that started it.**

Each worker is placed in a Windows Job Object created with KILL_ON_JOB_CLOSE.
Terminating the job ends the worker, the Playwright driver it started and the
Chromium processes under that, in one call, without walking a process tree
that is already coming apart. The job handle belongs to the API process, so
if the API dies by any route — a crash, Task Manager, the console closed —
the OS closes the handle and every browser it started goes with it. A psutil
snapshot of the tree is kept as a fallback for anything that escaped the job.
"""

import atexit
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
REPO = BACKEND.parent
# Every worker's TEMP is a folder named with this, under the system temp. A
# worker deletes its own on exit; one whose API was killed outright cannot,
# and its folder stays behind.
TEMP_PREFIX = "atv-"

_WIN = sys.platform == "win32"
_BROWSER_NAMES = ("chrome", "chromium", "headless_shell")


# ── Windows Job Objects ──────────────────────────────────────────────────

if _WIN:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BASIC_LIMIT),
                    ("IoInfo", _IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _BASIC_ACCOUNTING(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_int64),
                    ("TotalKernelTime", ctypes.c_int64),
                    ("ThisPeriodTotalUserTime", ctypes.c_int64),
                    ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                    ("TotalPageFaultCount", wintypes.DWORD),
                    ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD),
                    ("TotalTerminatedProcesses", wintypes.DWORD)]

    _ACCOUNTING_INFO = 1                    # JobObjectBasicAccountingInformation
    _EXTENDED_INFO = 9                      # JobObjectExtendedLimitInformation
    _KILL_ON_JOB_CLOSE = 0x2000

    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                             wintypes.LPVOID, wintypes.DWORD]
    _k32.QueryInformationJobObject.restype = wintypes.BOOL
    _k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                               wintypes.DWORD, wintypes.LPDWORD]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]


class _Job:
    """One kill-on-close Job Object holding one worker and its descendants."""

    def __init__(self, handle):
        self._h = handle

    @classmethod
    def holding(cls, popen):
        """-> a _Job the process was assigned to, or None. None is not an
        error: the psutil fallback still kills the tree, only less surely.

        There is a gap between Popen starting the worker and the assignment
        below. The worker spends far longer than that importing before it
        starts the Playwright driver, so the driver and Chromium are created
        inside the job and inherit it."""
        if not _WIN:
            return None
        h = _k32.CreateJobObjectW(None, None)
        if not h:
            return None
        info = _EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        ok = (_k32.SetInformationJobObject(h, _EXTENDED_INFO, ctypes.byref(info), ctypes.sizeof(info))
              and _k32.AssignProcessToJobObject(h, wintypes.HANDLE(int(popen._handle))))
        if not ok:
            _k32.CloseHandle(h)
            return None
        return cls(h)

    def terminate(self):
        if self._h:
            _k32.TerminateJobObject(self._h, 1)

    def peak_mb(self):
        """Peak committed memory of everything that ran in the job."""
        if not self._h:
            return None
        info = _EXTENDED_LIMIT()
        if not _k32.QueryInformationJobObject(self._h, _EXTENDED_INFO, ctypes.byref(info),
                                              ctypes.sizeof(info), None):
            return None
        return round(info.PeakJobMemoryUsed / 2**20)

    def active(self):
        """How many processes of the job are still alive, or None."""
        if not self._h:
            return None
        info = _BASIC_ACCOUNTING()
        if not _k32.QueryInformationJobObject(self._h, _ACCOUNTING_INFO, ctypes.byref(info),
                                              ctypes.sizeof(info), None):
            return None
        return info.ActiveProcesses

    def close(self):
        """Closing the last handle kills whatever is still in the job."""
        if self._h:
            _k32.CloseHandle(self._h)
            self._h = None


# ── workers ──────────────────────────────────────────────────────────────

_LIVE = set()
_LIVE_LOCK = threading.Lock()


def worker_command(job_path):
    """The command line for one target. Tests swap this for a stand-in."""
    return [sys.executable, str(BACKEND / "worker.py"), str(job_path)]


def _tree(pid):
    try:
        import psutil
        return psutil.Process(pid).children(recursive=True)
    except Exception:
        return []


class WorkerProc:
    def __init__(self, popen, job, temp_dir, log):
        self._p, self._job, self._temp, self._log = popen, job, temp_dir, log
        self.pid = popen.pid

    def wait(self, timeout):
        """-> the exit code, or None if still running after `timeout`."""
        try:
            return self._p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def kill_browser(self):
        """Kill only this worker's Chromium. The stuck Playwright call then
        fails at once and the worker can still write meta.json — the same
        effect the old process-wide kill had on its one target."""
        for c in _tree(self.pid):
            try:
                if any(n in (c.name() or "").lower() for n in _BROWSER_NAMES):
                    c.kill()
            except Exception:
                pass

    def kill(self):
        # Snapshot first: once the driver is gone its Chromium children no
        # longer hang off this pid, and a walk taken afterwards misses them.
        stragglers = _tree(self.pid)
        self._stragglers = stragglers
        if self._job:
            self._job.terminate()
        try:
            self._p.kill()
        except Exception:
            pass
        for c in stragglers:
            try:
                c.kill()
            except Exception:
                pass

    _stragglers = ()

    def peak_mem_mb(self):
        return self._job.peak_mb() if self._job else None

    def _left(self):
        """How many processes of this worker are still alive."""
        n = self._job.active() if self._job else None
        if n is not None:
            return n
        left = 0
        for c in self._stragglers:
            try:
                if c.is_running():
                    left += 1
            except Exception:
                pass
        return left

    def _wait_gone(self, seconds):
        deadline = time.monotonic() + seconds
        while self._left() and time.monotonic() < deadline:
            time.sleep(0.05)
        return not self._left()

    def close(self):
        """After the worker has exited: end anything it left behind, and
        delete its temp folder (Chromium's throwaway profile lives there).

        A killed Chromium takes a moment to let go of its files, and Windows
        will not delete a folder with an open file in it — so the folder was
        being left behind exactly when a target had been killed. Wait for the
        processes to be gone first, and try the delete more than once."""
        if not self._wait_gone(3):
            if self._job:
                self._job.terminate()
            self._wait_gone(3)
        if self._job:
            self._job.close()
        try:
            self._log.close()
        except Exception:
            pass
        _remove_tree(self._temp)
        with _LIVE_LOCK:
            _LIVE.discard(self)


def _remove_tree(path, tries=6, pause=0.3):
    for _ in range(tries):
        shutil.rmtree(path, ignore_errors=True)
        if not Path(path).exists():
            return
        time.sleep(pause)


def launch(job_path, log_path, temp_dir):
    """Start one worker. -> WorkerProc.

    - TEMP/TMP point at a folder of its own, outside OneDrive. A killed
      Playwright leaves its profile folder behind; this way it is deleted
      with the folder instead of piling up.
    - No console window, so Ctrl+C in the API's console does not reach every
      Chromium at once; they end through the job when the API exits.
    - Output goes to worker.log beside the target's artifacts.
    """
    temp_dir = Path(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TEMP=str(temp_dir), TMP=str(temp_dir),
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    # The worker starts in the repo, not where this process was started, so a
    # relative path here would point somewhere else — and the vision fallback
    # quietly turns itself off when its credentials file is not found.
    cred = env.get("GOOGLE_APPLICATION_CREDENTIALS")
    if cred and not os.path.isabs(cred):
        env["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(cred)
    log = open(log_path, "ab")
    try:
        popen = subprocess.Popen(
            worker_command(job_path), cwd=str(REPO), env=env,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if _WIN else 0)
    except Exception:
        log.close()
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    w = WorkerProc(popen, _Job.holding(popen), temp_dir, log)
    with _LIVE_LOCK:
        _LIVE.add(w)
    return w


def kill_all():
    """Every worker still running. Registered at exit; the jobs would end
    them anyway when this process goes, this just does not wait for that."""
    with _LIVE_LOCK:
        live = list(_LIVE)
    for w in live:
        w.kill()
        w.close()


atexit.register(kill_all)
