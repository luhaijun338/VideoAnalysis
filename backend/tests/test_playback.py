from video_analysis.playback import player_seek_seconds


def test_seek_minus_one_second() -> None:
    assert player_seek_seconds(123000) == 122.0


def test_seek_floor_zero() -> None:
    assert player_seek_seconds(400) == 0.0
