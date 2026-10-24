from datetime import datetime, timezone

from ingest.common import (
    request_interval_seconds,
    robots_allows,
    robots_readable,
    scrub,
    visit_open,
)

GDACS = """
User-agent: *
Disallow:
Request-rate: 1/60 # one page every 60 seconds
Visit-time: 0400-0645 # UTC
"""


def test_gdacs_rate_and_visit_window():
    assert robots_allows(GDACS, "/gdacsapi/api/events/geteventlist/SEARCH")
    assert request_interval_seconds(GDACS) == 60
    assert visit_open(GDACS, datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc))
    assert not visit_open(GDACS, datetime(2026, 10, 24, 3, 59, tzinfo=timezone.utc))
    assert visit_open(GDACS, datetime(2026, 10, 24, 6, 45, tzinfo=timezone.utc))
    assert not visit_open(GDACS, datetime(2026, 10, 24, 6, 46, tzinfo=timezone.utc))


def test_no_visit_time_means_any_hour():
    robots = "User-agent: *\nDisallow:\n"
    assert visit_open(robots, datetime(2026, 10, 24, 1, 0, tzinfo=timezone.utc))
    assert request_interval_seconds(robots) is None


def test_scrub_query_secret():
    text = "https://example.test/flood?api_key=supersecretvalue&limit=1"
    cleaned = scrub(text, "supersecretvalue")
    assert "supersecretvalue" not in cleaned
    assert "api_key=REDACTED" in cleaned


def test_scrub_signed_filestore_query():
    text = (
        "https://s3.example/file.csv?AWSAccessKeyId=AKIAEXAMPLE&"
        "Signature=abc%3D&x-amz-security-token=tokentokentoken&Expires=1"
    )
    cleaned = scrub(text)
    assert "AKIAEXAMPLE" not in cleaned
    assert "tokentokentoken" not in cleaned
    assert "Expires=1" in cleaned


def test_html_error_page_is_not_a_robots_file():
    page = "<html><body>Not Acceptable</body></html>"
    assert not robots_readable(page)
    assert robots_allows(page, "/gdacsapi/api/events/geteventlist/SEARCH")
