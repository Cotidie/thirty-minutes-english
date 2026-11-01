"""What each paid feature costs, in credits: about one cent each, rounded up from what it costs us."""

from datetime import timedelta

PRICES: dict[str, int] = {
    "session": 200,
    "session_cancelled": 100,
    "redraw": 10,
    "practice_voice": 10,
    "practice_feedback": 10,
    "summary_voice": 10,
    "summary_feedback": 10,
    "read_aloud_token": 5,
    "read_aloud_voice": 5,
    "speech": 1,
}

# How long the browser has to say a round connected: Gemini's two-minute window, its setup wait, and a margin.
CONFIRM_WINDOW = timedelta(minutes=3)
# How long after that it may still report the round dropped: the life of Gemini's token.
REPORT_WINDOW = timedelta(minutes=30)
