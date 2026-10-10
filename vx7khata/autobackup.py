"""Automatic + manual database backups to Downloads/"SJB KHATA BACKUP 24". No Qt here (unit-testable).

* Every backup is a NEW file ``SJB_KHATA_BACKUP_YYYY-MM-DD_HHMMSS.db`` (never overwrites, never deleted by the app).
* The snapshot is taken with SQLite's online-backup API from a read-only connection, so the live database is never
  modified and the app can stay open. The copy is re-opened and integrity-checked before it counts as a success.
* State (enabled flag, folder, last success, status, history) lives in ``backup_state.json`` / ``backup_history.jsonl``
  next to the database, NOT inside it: a restore cannot rewind it and the headless scheduled run needs no write access
  to the database.
* The same code runs from the app (timer / button) and from Windows Task Scheduler (``main.py --backup``).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from . import backup as backup_mod
from . import paths

FOLDER_NAME = "SJB KHATA BACKUP 24"
FILE_PREFIX = "SJB_KHATA_BACKUP_"
INTERVAL = timedelta(hours=24)
TASK_NAME = "VX7 KHATA PRO Automatic Backup"
STATE_FILE = "backup_state.json"
HISTORY_FILE = "backup_history.jsonl"
LOCK_FILE = "backup.lock"
LOCK_STALE_SECONDS = 600
_NAME = re.compile(r"SJB_KHATA_BACKUP_(\d{4}-\d{2}-\d{2})_(\d{6})(?:_(\d+))?\.db")
_FMT = "%Y-%m-%dT%H:%M:%S"

ENV_OVERRIDE = "VX7_BACKUP_DIR"   # tests / portable use


class BackupBusy(backup_mod.BackupError):
    """Another backup is running right now."""


def default_backup_dir() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    return Path(override) if override else paths.downloads_dir() / FOLDER_NAME


@dataclass(frozen=True)
class Status:
    enabled: bool
    folder: Path
    status: str                    # "Never run", "Success", "In Progress" or "Failed"
    last_success: Optional[datetime]
    last_error: str
    next_due: Optional[datetime]   # None when automatic backup is off
    backups_in_folder: int


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


class BackupManager:
    def __init__(self, db_path, clock: Optional[Callable[[], datetime]] = None):
        self.db_path = Path(db_path)
        self._clock = clock or _now
        self.data_dir = self.db_path.parent

    # ---------------------------------------------------------------- time / state
    def now(self) -> datetime:
        n = self._clock()
        return n.replace(tzinfo=None, microsecond=0) if n.tzinfo else n.replace(microsecond=0)

    def _state_path(self) -> Path:
        return self.data_dir / STATE_FILE

    def load_state(self) -> dict:
        try:
            data = json.loads(self._state_path().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self, **changes) -> None:
        state = self.load_state()
        state.update(changes)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.data_dir, prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=1)
            os.replace(tmp, self._state_path())
        finally:
            Path(tmp).unlink(missing_ok=True)

    def _log(self, ok: bool, kind: str, message: str, path: Optional[Path] = None) -> None:
        line = {"at": self.now().strftime(_FMT), "ok": ok, "kind": kind, "message": message,
                "file": str(path) if path else ""}
        try:
            with open(self.data_dir / HISTORY_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def history(self, limit: int = 200) -> list[dict]:
        """Newest first: every backup attempt (success or failure)."""
        try:
            lines = (self.data_dir / HISTORY_FILE).read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for ln in reversed(lines):
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
            if len(out) >= limit:
                break
        return out

    # ---------------------------------------------------------------- settings
    def enabled(self) -> bool:
        return bool(self.load_state().get("enabled", True))

    def set_enabled(self, on: bool) -> None:
        self._save_state(enabled=bool(on))

    def folder(self) -> Path:
        custom = str(self.load_state().get("folder") or "").strip()
        return Path(custom) if custom else default_backup_dir()

    def set_folder(self, folder: Optional[str]) -> None:
        """Choose a folder; empty/None goes back to Downloads/SJB KHATA BACKUP 24."""
        self._save_state(folder=str(folder or "").strip())

    # ---------------------------------------------------------------- queries
    def _files(self) -> list[Path]:
        f = self.folder()
        return sorted((p for p in f.glob(FILE_PREFIX + "*.db") if _NAME.fullmatch(p.name)),
                      key=lambda p: self._stamp(p) or datetime.min) if f.is_dir() else []

    @staticmethod
    def _stamp(path: Path) -> Optional[datetime]:
        m = _NAME.fullmatch(path.name)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H%M%S")
        except ValueError:
            return None

    def last_success(self) -> Optional[datetime]:
        """Newest of: the recorded last success and the newest valid-named file (so a restart never duplicates)."""
        times = []
        raw = self.load_state().get("last_success")
        if raw:
            try:
                times.append(datetime.strptime(raw, _FMT))
            except ValueError:
                pass
        files = self._files()
        if files and self._stamp(files[-1]):
            times.append(self._stamp(files[-1]))
        return max(times) if times else None

    def is_due(self) -> bool:
        last = self.last_success()
        now = self.now()
        if last is None or last > now:   # a stamp in the future (clock was changed) does not count
            return True
        return now - last >= INTERVAL

    def next_due(self) -> Optional[datetime]:
        if not self.enabled():
            return None
        last = self.last_success()
        if last is None:
            return self.now()
        return max(last + INTERVAL, self.now()) if last <= self.now() else self.now()

    def status(self) -> Status:
        st = self.load_state()
        label = st.get("status") or "Never run"
        if label == "In Progress" and not self._lock_active():
            label = "Failed"   # the app/task died in the middle of a backup
        return Status(self.enabled(), self.folder(), label, self.last_success(), st.get("last_error", ""),
                      self.next_due(), len(self._files()))

    # ---------------------------------------------------------------- locking
    def _lock_path(self) -> Path:
        return self.data_dir / LOCK_FILE

    def _lock_active(self) -> bool:
        try:
            age = datetime.now().timestamp() - self._lock_path().stat().st_mtime
        except OSError:
            return False
        return age < LOCK_STALE_SECONDS

    def _acquire(self) -> None:
        lp = self._lock_path()
        for _ in range(2):
            try:
                fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return
            except FileExistsError:
                if self._lock_active():
                    raise BackupBusy("Another backup is already running. Please wait a minute.")
                lp.unlink(missing_ok=True)   # stale lock from a crashed run
        raise BackupBusy("Another backup is already running. Please wait a minute.")

    def _release(self) -> None:
        self._lock_path().unlink(missing_ok=True)

    # ---------------------------------------------------------------- the backup itself
    def _new_path(self, folder: Path) -> Path:
        stamp = self.now().strftime("%Y-%m-%d_%H%M%S")
        dest = folder / f"{FILE_PREFIX}{stamp}.db"
        n = 1
        while dest.exists():            # never overwrite
            n += 1
            dest = folder / f"{FILE_PREFIX}{stamp}_{n}.db"
        return dest

    def run_backup(self, kind: str = "manual", conn: Optional[sqlite3.Connection] = None) -> Path:
        """Create one verified backup now. Raises BackupError (with a plain-language message) on failure."""
        folder = self.folder()
        self._acquire()
        try:
            self._save_state(status="In Progress", last_attempt=self.now().strftime(_FMT))
            try:
                folder.mkdir(parents=True, exist_ok=True)
                probe = folder / ".write-test"
                probe.write_text("ok")
                probe.unlink()
            except OSError as exc:
                raise backup_mod.BackupError(
                    f"Cannot write to the backup folder '{folder}'. Check that the folder exists, the drive is "
                    f"connected and you are allowed to save there. ({exc.strerror or exc})") from exc
            if not self.db_path.is_file():
                raise backup_mod.BackupError(f"The database file was not found: {self.db_path}")
            dest = self._new_path(folder)
            own = conn is None
            src = conn
            try:
                if own:
                    src = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
                backup_mod.create_backup(src, dest)          # snapshot to .part, verify, then rename
            finally:
                if own and src is not None:
                    src.close()
            info = backup_mod.validate_backup(dest)          # re-open the final file: exists, readable, intact
            if not os.access(dest, os.R_OK):
                raise backup_mod.BackupError("The backup was written but cannot be read back.")
            self._save_state(status="Success", last_success=self.now().strftime(_FMT), last_error="")
            self._log(True, kind, f"{info.customers} customers, {info.transactions} entries, "
                                  f"{info.size_bytes // 1024} KB", dest)
            return dest
        except Exception as exc:   # noqa: BLE001 - record then re-raise
            if isinstance(exc, BackupBusy):
                raise
            msg = str(exc) if isinstance(exc, backup_mod.BackupError) else f"Unexpected error: {exc}"
            self._save_state(status="Failed", last_error=msg)
            self._log(False, kind, msg)
            if isinstance(exc, backup_mod.BackupError):
                raise
            raise backup_mod.BackupError(msg) from exc
        finally:
            self._release()

    def run_if_due(self, kind: str = "auto", conn: Optional[sqlite3.Connection] = None) -> Optional[Path]:
        """Automatic backup: only when enabled AND 24 h have passed since the newest backup."""
        if not self.enabled() or not self.is_due():
            return None
        try:
            return self.run_backup(kind, conn)
        except BackupBusy:
            return None


# ------------------------------------------------------------------ Windows Task Scheduler
def _is_windows() -> bool:
    return os.name == "nt"


def _command() -> tuple[str, str]:
    """(program, arguments) that runs a headless backup."""
    if getattr(sys, "frozen", False):
        return sys.executable, "--backup"
    main = Path(__file__).resolve().parent.parent / "main.py"
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return str(pyw if pyw.exists() else exe), f'"{main}" --backup'


def task_xml(start: datetime, program: str, arguments: str) -> str:
    """Task Scheduler XML: checks every hour (a backup is only made when 24 h old, so no duplicates), runs as soon as possible after a missed start (PC was off), only for this user."""
    from xml.sax.saxutils import escape
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>VX7 KHATA PRO: automatic database backup every 24 hours</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <Repetition><Interval>PT1H</Interval><Duration>P1D</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>{start.strftime(_FMT)}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(program)}</Command><Arguments>{escape(arguments)}</Arguments></Exec></Actions>
</Task>
"""


def install_task(start: Optional[datetime] = None, runner=subprocess.run) -> tuple[bool, str]:
    """Create/replace the per-user daily task. Returns (ok, message). Windows only; harmless elsewhere."""
    if not _is_windows():
        return False, "Windows Task Scheduler is only available on Windows."
    program, args = _command()
    start = start or (datetime.now().replace(microsecond=0) + timedelta(minutes=5))
    xml_path = Path(tempfile.gettempdir()) / "vx7_backup_task.xml"
    try:
        xml_path.write_text(task_xml(start, program, args), encoding="utf-16")
        res = runner(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
                     capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Could not set up Windows Task Scheduler: {exc}"
    finally:
        xml_path.unlink(missing_ok=True)
    if res.returncode != 0:
        return False, f"Windows Task Scheduler refused the task: {(res.stderr or res.stdout).strip()}"
    return True, "Windows Task Scheduler will run the backup every 24 hours, even when the app is closed."


def remove_task(runner=subprocess.run) -> tuple[bool, str]:
    if not _is_windows():
        return True, ""
    try:
        res = runner(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True, timeout=30,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return True, "Scheduled backup removed."


def task_exists(runner=subprocess.run) -> bool:
    if not _is_windows():
        return False
    try:
        return runner(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True, text=True, timeout=30,
                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def cli_main() -> int:
    """``VX7 KHATA PRO.exe --backup``: headless run used by Task Scheduler. Exit 0 = ok or nothing due."""
    mgr = BackupManager(paths.db_path())
    try:
        mgr.run_if_due("scheduled")
    except backup_mod.BackupError:
        return 1
    return 0
