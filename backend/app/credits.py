"""What each paid feature costs, in credits: about one cent each, rounded up from what it costs us."""

PRICES: dict[str, int] = {
    "session": 200,
    "redraw": 10,
    "practice_voice": 10,
    "practice_feedback": 10,
    "summary_voice": 10,
    "summary_feedback": 10,
    "read_aloud_token": 5,
    "read_aloud_voice": 5,
    "speech": 1,
}
