import os
import sys
import subprocess
import logging
import httpx
from PyQt6.QtCore import QObject, pyqtSignal, QThread
from .config import APP_VERSION, get_app_dir

logger = logging.getLogger(__name__)

class UpdateDownloader(QThread):
    """Thread for downloading update asset."""
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, url: str, dest_path: str):
        super().__init__()
        self.url = url
        self.dest_path = dest_path

    def run(self):
        try:
            with httpx.stream("GET", self.url, follow_redirects=True) as response:
                if response.status_code != 200:
                    self.finished.emit(False, f"HTTP {response.status_code}")
                    return

                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0

                with open(self.dest_path, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            percent = int((downloaded / total) * 100)
                            self.progress.emit(percent)

                self.finished.emit(True, self.dest_path)
        except Exception as e:
            logger.exception("Download failed")
            self.finished.emit(False, str(e))

class UpdateChecker(QThread):
    """Thread for checking for updates via GitHub API."""
    update_available = pyqtSignal(str, str, str)  # version, description, download_url
    not_found = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, api_url: str, manual: bool = False):
        super().__init__()
        self.api_url = api_url
        self.manual = manual

    def run(self):
        try:
            response = httpx.get(self.api_url, follow_redirects=True)
            if response.status_code == 200:
                data = response.json()
                latest_version = data["tag_name"].lstrip("v")

                if self._is_newer(latest_version, APP_VERSION):
                    # Find S-Flow.exe in assets
                    download_url = None
                    for asset in data.get("assets", []):
                        if asset["name"] == "S-Flow.exe":
                            download_url = asset["browser_download_url"]
                            break

                    if download_url:
                        self.update_available.emit(
                            latest_version,
                            data.get("body", ""),
                            download_url
                        )
                    else:
                        logger.warning("No S-Flow.exe found in latest release assets")
                        if self.manual:
                            self.not_found.emit()
                else:
                    logger.info(f"App is up to date (Local: {APP_VERSION}, Remote: {latest_version})")
                    if self.manual:
                        self.not_found.emit()
            else:
                logger.error(f"GitHub API returned {response.status_code}")
                if self.manual:
                    self.error.emit(f"GitHub API Error: {response.status_code}")
        except Exception as e:
            logger.exception("Update check failed")
            if self.manual:
                self.error.emit(str(e))

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        """Simple semantic version comparison."""
        try:
            l_parts = [int(p) for p in latest.split(".")]
            c_parts = [int(p) for p in current.split(".")]
            return l_parts > c_parts
        except ValueError:
            return latest > current


class UpdateManager(QObject):
    """Manages application updates via GitHub Releases."""
    update_available = pyqtSignal(str, str, str)  # version, description, download_url
    download_progress = pyqtSignal(int)
    download_finished = pyqtSignal(bool, str)
    error = pyqtSignal(str)
    not_found = pyqtSignal()

    def __init__(self, repo: str = "id-ex/S-Flow"):
        super().__init__()
        self.repo = repo
        self.api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        self.downloader = None

    def check_for_updates(self, manual: bool = False):
        """Check for latest release on GitHub."""
        self._checker = UpdateChecker(self.api_url, manual)
        self._checker.update_available.connect(self.update_available.emit)
        self._checker.not_found.connect(self.not_found.emit)
        self._checker.error.connect(self.error.emit)
        self._checker.start()


    def start_download(self, url: str):
        """Start downloading the new executable."""
        dest_path = os.path.join(get_app_dir(), "S-Flow.exe.new")
        self.downloader = UpdateDownloader(url, dest_path)
        self.downloader.progress.connect(self.download_progress.emit)
        self.downloader.finished.connect(self.download_finished.emit)
        self.downloader.start()

    def apply_update(self):
        """Generate updater script and exit to replace EXE."""
        if not getattr(sys, "frozen", False):
            logger.warning("Not running as frozen EXE, skip update apply")
            return

        app_dir = get_app_dir()
        exe_path = os.path.join(app_dir, "S-Flow.exe")
        new_exe_path = os.path.join(app_dir, "S-Flow.exe.new")
        bat_path = os.path.join(app_dir, "updater.bat")

        if not os.path.exists(new_exe_path):
            logger.error("New EXE not found")
            return

        # Create batch script to swap files
        # It waits for process to end, swaps, restarts, and deletes itself
        bat_content = f"""@echo off
set _MEIPASS=
timeout /t 1 /nobreak > nul
:loop
tasklist /fi "imagename eq S-Flow.exe" | find /i "S-Flow.exe" > nul
if %errorlevel% equ 0 (
    timeout /t 1 /nobreak > nul
    goto loop
)
del "{exe_path}"
move "{new_exe_path}" "{exe_path}"
start "" "{exe_path}"
del "%~f0"
"""
        try:
            with open(bat_path, "w", encoding="cp1251") as f:
                f.write(bat_content)

            # Create a clean environment for the child process to avoid PyInstaller DLL issues
            env = os.environ.copy()
            # Remove PyInstaller-specific environment variables
            meipass = getattr(sys, "_MEIPASS", None)
            for var in ["_MEIPASS", "PYI_CHILD_STOP", "PYI_PARENT_STOP", "PYTHONPATH", "PYTHONHOME"]:
                if var in env:
                    del env[var]

            # Also clean PATH to remove any references to the current temporary directory
            if meipass:
                paths = env.get("PATH", "").split(os.pathsep)
                # Remove any entry that contains the current _MEIPASS path
                new_paths = [p for p in paths if meipass not in p]
                if len(new_paths) < len(paths):
                    env["PATH"] = os.pathsep.join(new_paths)
                    logger.debug(f"Cleaned PATH for updater: removed references to {meipass}")

            logger.info("Launching updater.bat and exiting...")
            # Use specific cmd.exe invocation to avoid shell=True injection risks
            subprocess.Popen(
                ["cmd.exe", "/c", bat_path],
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
                env=env,
            )
            sys.exit(0)
        except Exception as e:
            logger.exception("Failed to apply update")
            self.error.emit(str(e))
