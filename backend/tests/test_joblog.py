import io
import logging

from app.generation.joblog import LOG_FORMAT, JobTag, job_logs, tag_job_logs


def record() -> logging.LogRecord:
    return logging.LogRecord("app.llm", logging.INFO, __file__, 1, "opus run: 1.0s", None, None)


def test_a_line_logged_inside_a_job_names_the_job():
    inside, outside = record(), record()
    with job_logs("ab12"):
        assert JobTag().filter(inside)
    JobTag().filter(outside)
    assert (inside.job, outside.job) == (" job ab12", "")


def test_the_job_tag_is_put_back_after_the_job():
    with job_logs("one"):
        with job_logs("two"):
            pass
        line = record()
        JobTag().filter(line)
    assert line.job == " job one"


def test_the_app_log_line_puts_the_job_after_the_logger_name():
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    tag_job_logs([handler])
    with job_logs("ab12"):
        handler.handle(record())
    handler.handle(record())
    assert out.getvalue().splitlines() == ["INFO app.llm job ab12: opus run: 1.0s", "INFO app.llm: opus run: 1.0s"]
