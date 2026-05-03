import hashlib
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .config import APP_VERSION, UPDATE_MANIFEST_URL, get_app_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    url: str
    sha256: str
    notes: str = ""
    size: int | None = None

    @classmethod
    def from_json(cls, data: dict, manifest_url: str) -> "UpdateManifest":
        version = str(data.get("version", "")).lstrip("v").strip()
        url = str(data.get("url", "")).strip()
        sha256 = str(data.get("sha256", "")).strip().lower()
        notes = str(data.get("notes", "")).strip()
        size_raw = data.get("size")

        if not version:
            raise ValueError("Update manifest is missing version")
        if not url:
            raise ValueError("Update manifest is missing url")
        if not sha256 or len(sha256) != 64:
            raise ValueError("Update manifest is missing valid sha256")

        if not url.startswith(("http://", "https://")):
            url = urljoin(manifest_url, url)

        size = None
        if size_raw not in (None, ""):
            size = int(size_raw)

        return cls(version=version, url=url, sha256=sha256, notes=notes, size=size)


def is_newer_version(latest: str, current: str) -> bool:
    """Return True when latest semantic version is newer than current."""
    try:
        latest_parts = [int(part) for part in latest.split(".")]
        current_parts = [int(part) for part in current.split(".")]
        max_len = max(len(latest_parts), len(current_parts))
        latest_parts += [0] * (max_len - len(latest_parts))
        current_parts += [0] * (max_len - len(current_parts))
        return latest_parts > current_parts
    except ValueError:
        return latest > current


def calculate_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class UpdateDownloader(QThread):
    """Download and verify update asset."""

    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, manifest: UpdateManifest, dest_path: str):
        super().__init__()
        self.manifest = manifest
        self.dest_path = dest_path

    def run(self):
        try:
            with httpx.stream(
                "GET",
                self.manifest.url,
                follow_redirects=True,
                timeout=60.0,
            ) as response:
                if response.status_code != 200:
                    self.finished.emit(False, f"HTTP {response.status_code}")
                    return

                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0

                with open(self.dest_path, "wb") as file:
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        file.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            self.progress.emit(int((downloaded / total) * 100))

            if self.manifest.size is not None:
                actual_size = os.path.getsize(self.dest_path)
                if actual_size != self.manifest.size:
                    self.finished.emit(
                        False,
                        f"Size mismatch: expected {self.manifest.size}, got {actual_size}",
                    )
                    return

            actual_hash = calculate_sha256(self.dest_path)
            if actual_hash.lower() != self.manifest.sha256:
                self.finished.emit(False, "SHA256 mismatch")
                return

            self.progress.emit(100)
            self.finished.emit(True, self.dest_path)
        except Exception as e:
            logger.exception("Download failed")
            self.finished.emit(False, str(e))


class UpdateChecker(QThread):
    """Check update manifest."""

    update_available = pyqtSignal(object)
    not_found = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, manifest_url: str, manual: bool = False):
        super().__init__()
        self.manifest_url = manifest_url
        self.manual = manual

    def run(self):
        try:
            response = httpx.get(
                self.manifest_url,
                follow_redirects=True,
                timeout=15.0,
            )
            if response.status_code != 200:
                message = f"Update manifest HTTP {response.status_code}"
                logger.error(message)
                if self.manual:
                    self.error.emit(message)
                return

            manifest = UpdateManifest.from_json(response.json(), self.manifest_url)
            if is_newer_version(manifest.version, APP_VERSION):
                self.update_available.emit(manifest)
                return

            logger.info(
                "App is up to date (local=%s, remote=%s)",
                APP_VERSION,
                manifest.version,
            )
            if self.manual:
                self.not_found.emit()
        except Exception as e:
            logger.exception("Update check failed")
            if self.manual:
                self.error.emit(str(e))


class UpdateManager(QObject):
    """Manages application updates via a static JSON manifest."""

    update_available = pyqtSignal(str, str, str)
    download_progress = pyqtSignal(int)
    download_finished = pyqtSignal(bool, str)
    error = pyqtSignal(str)
    not_found = pyqtSignal()

    def __init__(self, manifest_url: str = UPDATE_MANIFEST_URL):
        super().__init__()
        self.manifest_url = manifest_url
        self.downloader: UpdateDownloader | None = None
        self.latest_manifest: UpdateManifest | None = None
        self._checker: UpdateChecker | None = None

    def check_for_updates(self, manual: bool = False):
        """Check for update manifest in a worker thread."""
        self._checker = UpdateChecker(self.manifest_url, manual)
        self._checker.update_available.connect(self._on_update_available)
        self._checker.not_found.connect(self.not_found.emit)
        self._checker.error.connect(self.error.emit)
        self._checker.start()

    def _on_update_available(self, manifest: UpdateManifest) -> None:
        self.latest_manifest = manifest
        self.update_available.emit(manifest.version, manifest.notes, manifest.url)

    def start_download(self, url: str | None = None):
        """Start downloading the executable from the latest manifest."""
        manifest = self.latest_manifest
        if manifest is None:
            self.download_finished.emit(False, "No update manifest loaded")
            return

        if url and url != manifest.url:
            logger.warning("Ignoring stale update URL argument: %s", url)

        dest_path = os.path.join(get_app_dir(), "S-Flow.exe.new")
        self.downloader = UpdateDownloader(manifest, dest_path)
        self.downloader.progress.connect(self.download_progress.emit)
        self.downloader.finished.connect(self.download_finished.emit)
        self.downloader.start()

    def apply_update(self):
        """Create updater command script and exit current frozen process."""
        if not getattr(sys, "frozen", False):
            logger.warning("Not running as frozen EXE, skip update apply")
            self.error.emit("Update can be applied only in the packaged EXE")
            return

        app_dir = get_app_dir()
        exe_path = os.path.join(app_dir, "S-Flow.exe")
        new_exe_path = os.path.join(app_dir, "S-Flow.exe.new")
        backup_path = os.path.join(app_dir, "S-Flow.exe.bak")
        updater_path = os.path.join(app_dir, "updater.cmd")
        updater_log = os.path.join(app_dir, "updater.log")
        pid = os.getpid()

        if not os.path.exists(new_exe_path):
            message = "New EXE not found"
            logger.error(message)
            self.error.emit(message)
            return

        script = self._build_updater_script(
            pid=pid,
            app_dir=app_dir,
            exe_path=exe_path,
            new_exe_path=new_exe_path,
            backup_path=backup_path,
            updater_log=updater_log,
        )

        try:
            with open(updater_path, "w", encoding="utf-8") as file:
                file.write(script)

            env = self._clean_child_env()
            logger.info("Launching updater.cmd and exiting current process")
            subprocess.Popen(
                ["cmd.exe", "/d", "/c", updater_path],
                cwd=app_dir,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
                env=env,
            )
            logging.shutdown()
            os._exit(0)
        except Exception as e:
            logger.exception("Failed to apply update")
            self.error.emit(str(e))

    @staticmethod
    def _clean_child_env() -> dict[str, str]:
        env = os.environ.copy()
        meipass = getattr(sys, "_MEIPASS", None)
        for var in [
            "_MEIPASS",
            "PYI_CHILD_STOP",
            "PYI_PARENT_STOP",
            "PYTHONPATH",
            "PYTHONHOME",
        ]:
            env.pop(var, None)

        if meipass:
            paths = env.get("PATH", "").split(os.pathsep)
            env["PATH"] = os.pathsep.join(path for path in paths if meipass not in path)

        return env

    @staticmethod
    def _build_updater_script(
        pid: int,
        app_dir: str,
        exe_path: str,
        new_exe_path: str,
        backup_path: str,
        updater_log: str,
    ) -> str:
        return f"""@echo off
setlocal EnableExtensions
set "APP_DIR={app_dir}"
set "EXE_PATH={exe_path}"
set "NEW_EXE={new_exe_path}"
set "BACKUP_EXE={backup_path}"
set "LOG_FILE={updater_log}"
set "APP_PID={pid}"

cd /d "%APP_DIR%"
echo [%date% %time%] updater started for pid %APP_PID% > "%LOG_FILE%"

for /l %%i in (1,1,60) do (
    tasklist /fi "PID eq %APP_PID%" | find "%APP_PID%" > nul
    if errorlevel 1 goto process_stopped
    timeout /t 1 /nobreak > nul
)

echo [%date% %time%] timeout waiting for process >> "%LOG_FILE%"
exit /b 1

:process_stopped
echo [%date% %time%] process stopped >> "%LOG_FILE%"

if not exist "%NEW_EXE%" (
    echo [%date% %time%] new exe not found >> "%LOG_FILE%"
    exit /b 1
)

if exist "%BACKUP_EXE%" del /f /q "%BACKUP_EXE%" >> "%LOG_FILE%" 2>&1
if exist "%EXE_PATH%" move /y "%EXE_PATH%" "%BACKUP_EXE%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] failed to backup old exe >> "%LOG_FILE%"
    exit /b 1
)

move /y "%NEW_EXE%" "%EXE_PATH%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] failed to install new exe, restoring backup >> "%LOG_FILE%"
    if exist "%BACKUP_EXE%" move /y "%BACKUP_EXE%" "%EXE_PATH%" >> "%LOG_FILE%" 2>&1
    exit /b 1
)

start "" /d "%APP_DIR%" "%EXE_PATH%"
if errorlevel 1 (
    echo [%date% %time%] failed to start new exe, restoring backup >> "%LOG_FILE%"
    del /f /q "%EXE_PATH%" >> "%LOG_FILE%" 2>&1
    if exist "%BACKUP_EXE%" move /y "%BACKUP_EXE%" "%EXE_PATH%" >> "%LOG_FILE%" 2>&1
    start "" /d "%APP_DIR%" "%EXE_PATH%"
    exit /b 1
)

echo [%date% %time%] update installed successfully >> "%LOG_FILE%"
del /f /q "%BACKUP_EXE%" >> "%LOG_FILE%" 2>&1
del /f /q "%~f0"
"""
