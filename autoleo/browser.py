from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .lingualeo_client import DEFAULT_CDP_URL


CHROME_PROFILE_NAME = "autoleo-profile"
LINGUALEO_URL = "https://lingualeo.com/"


def chrome_profile_dir() -> Path:
    return Path(tempfile.gettempdir()) / CHROME_PROFILE_NAME


def find_chrome_executable() -> Path | None:
    candidates: list[Path] = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe"
        )

    chrome_on_path = shutil.which("chrome") or shutil.which("chrome.exe")
    if chrome_on_path:
        candidates.append(Path(chrome_on_path))

    return next((candidate for candidate in candidates if candidate.is_file()), None)


def open_autoleo_chrome() -> Path:
    chrome_executable = find_chrome_executable()
    if chrome_executable is None:
        raise FileNotFoundError(
            "Google Chrome не найден. Установите Chrome и попробуйте снова."
        )

    profile_dir = chrome_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(chrome_executable),
            "--remote-debugging-port=9223",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            LINGUALEO_URL,
        ],
        close_fds=True,
    )
    return profile_dir


def autoleo_chrome_is_running() -> bool:
    try:
        with urllib.request.urlopen(f"{DEFAULT_CDP_URL}/json/version", timeout=0.5):
            return True
    except (OSError, urllib.error.URLError):
        return False


def clear_chrome_profile() -> bool:
    temp_root = Path(tempfile.gettempdir()).resolve()
    profile_dir = chrome_profile_dir()
    resolved_profile = profile_dir.resolve()
    expected_profile = temp_root / CHROME_PROFILE_NAME

    if resolved_profile != expected_profile or profile_dir.name != CHROME_PROFILE_NAME:
        raise RuntimeError("Отказано: путь профиля Chrome не прошёл проверку безопасности.")

    if not profile_dir.exists():
        return False

    shutil.rmtree(profile_dir)
    return True
