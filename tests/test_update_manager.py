import hashlib
import os


def test_update_manifest_parses_relative_url():
    from core.update_manager import UpdateManifest

    manifest = UpdateManifest.from_json(
        {
            "version": "v1.10.7",
            "url": "S-Flow.exe",
            "sha256": "a" * 64,
            "size": 123,
            "notes": "Test release",
        },
        "https://example.com/releases/latest/download/update.json",
    )

    assert manifest.version == "1.10.7"
    assert manifest.url == "https://example.com/releases/latest/download/S-Flow.exe"
    assert manifest.sha256 == "a" * 64
    assert manifest.size == 123
    assert manifest.notes == "Test release"


def test_update_manifest_rejects_missing_hash():
    from core.update_manager import UpdateManifest

    try:
        UpdateManifest.from_json(
            {"version": "1.10.7", "url": "S-Flow.exe"},
            "https://example.com/update.json",
        )
    except ValueError as exc:
        assert "sha256" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_semantic_version_compare_pads_parts():
    from core.update_manager import is_newer_version

    assert is_newer_version("1.10.7", "1.10.6") is True
    assert is_newer_version("1.10.6", "1.10.6") is False
    assert is_newer_version("1.10.6.1", "1.10.6") is True
    assert is_newer_version("1.10", "1.10.1") is False


def test_calculate_sha256():
    from core.update_manager import calculate_sha256

    project_root = os.path.dirname(os.path.dirname(__file__))
    file_path = os.path.join(project_root, "tests", ".sha-test.bin")
    try:
        with open(file_path, "wb") as file:
            file.write(b"test executable")

        expected = hashlib.sha256(b"test executable").hexdigest()
        assert calculate_sha256(file_path) == expected
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def test_updater_script_uses_pid_backup_and_restart():
    from core.update_manager import UpdateManager

    script = UpdateManager._build_updater_script(
        pid=1234,
        app_dir=r"C:\App",
        exe_path=r"C:\App\S-Flow.exe",
        new_exe_path=r"C:\App\S-Flow.exe.new",
        backup_path=r"C:\App\S-Flow.exe.bak",
        updater_log=r"C:\App\updater.log",
    )

    assert 'tasklist /fi "PID eq %APP_PID%"' in script
    assert 'move /y "%EXE_PATH%" "%BACKUP_EXE%"' in script
    assert 'move /y "%NEW_EXE%" "%EXE_PATH%"' in script
    assert 'start "" /d "%APP_DIR%" "%EXE_PATH%"' in script
    assert "failed to install new exe, restoring backup" in script
    assert "APP_PID=1234" in script


def test_release_script_exists():
    project_root = os.path.dirname(os.path.dirname(__file__))

    assert os.path.exists(os.path.join(project_root, "scripts", "build-release.ps1"))
    assert os.path.exists(os.path.join(project_root, "scripts", "publish-release.ps1"))
