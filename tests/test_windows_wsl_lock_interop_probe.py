import json

import pytest

from scripts import probe_windows_wsl_lock_interop as probe


def test_parse_status_requires_one_known_status() -> None:
    assert probe.parse_status(
        "\nACQUIRED\n",
        allowed=frozenset({"ACQUIRED", "BLOCKED"}),
    ) == "ACQUIRED"

    with pytest.raises(probe.ProbeError):
        probe.parse_status(
            "ACQUIRED\nBLOCKED\n",
            allowed=frozenset({"ACQUIRED", "BLOCKED"}),
        )
    with pytest.raises(probe.ProbeError):
        probe.parse_status("unknown", allowed=frozenset({"ACQUIRED", "BLOCKED"}))


def test_report_is_path_free_and_marks_incompatible_results() -> None:
    report = probe.build_report(
        host={
            "windows_product": "Microsoft Windows 11 Pro",
            "windows_version": "10.0.26100.0",
            "powershell_version": "5.1.26100.1",
            "wsl_kernel": "6.6.87.2-microsoft-standard-WSL2",
            "python_version": "3.12.11",
        },
        results=[
            {
                "direction": "wsl_flock_to_windows_filestream",
                "holder": "wsl_flock",
                "contender": "windows_filestream_lock",
                "contender_result": "acquired",
                "compatible": False,
            },
            {
                "direction": "windows_filestream_to_wsl_flock",
                "holder": "windows_filestream_lock",
                "contender": "wsl_flock",
                "contender_result": "acquired",
                "compatible": False,
            },
        ],
        cleanup="completed",
    )

    encoded = json.dumps(report, sort_keys=True)
    assert report["overall_compatible"] is False
    assert report["cleanup"] == "completed"
    assert "/mnt/" not in encoded
    assert "C:\\" not in encoded
