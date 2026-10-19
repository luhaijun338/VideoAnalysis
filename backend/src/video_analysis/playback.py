def player_seek_seconds(t_start_ms: int, lead_ms: int = 1000) -> float:
    return max(0, t_start_ms - lead_ms) / 1000.0
