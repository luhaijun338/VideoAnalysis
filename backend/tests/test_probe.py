from pathlib import Path

import pytest

from video_analysis.probe import ProbeError, probe_video, validate_upload


def test_reject_bad_suffix() -> None:
    with pytest.raises(ProbeError, match="format"):
        validate_upload("note.txt", 100)


def test_reject_oversize() -> None:
    with pytest.raises(ProbeError, match="size"):
        validate_upload("a.mp4", 4 * 1024 * 1024 * 1024 + 1)


def test_accept_mp4_under_limit() -> None:
    validate_upload("操作.mp4", 1024)


def test_probe_raises_when_ffprobe_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr("video_analysis.probe.subprocess.run", fake_run)
    with pytest.raises(ProbeError, match="duration"):
        probe_video(tmp_path / "missing.mp4")


def test_probe_parses_duration_seconds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 0
        stdout = "12.5"
        stderr = ""

    monkeypatch.setattr("video_analysis.probe.subprocess.run", lambda *a, **k: Result())
    assert probe_video(tmp_path / "a.mp4") == 12500
