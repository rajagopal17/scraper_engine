from datetime import date

from scraper_engine.validate import compute_active, validate_record


def test_valid_record_with_missing_optional_fields_is_ok():
    result = validate_record({"project_details": "text", "region": None, "start_date": "2026-01-01"})
    assert result.ok
    assert result.reasons == []


def test_empty_record_is_rejected():
    result = validate_record({"project_details": None, "region": ""})
    assert not result.ok


def test_bad_date_format_is_rejected():
    result = validate_record({"start_date": "not-a-date"})
    assert not result.ok
    assert "start_date" in result.reasons[0]


def test_end_before_start_is_rejected():
    result = validate_record({"start_date": "2026-05-01", "end_date": "2026-01-01"})
    assert not result.ok


def test_iso_datetime_with_time_and_offset_is_accepted():
    """AI extraction commonly returns full ISO-8601 datetimes rather than bare
    dates; a real date must not be rejected just for carrying a time/offset."""
    result = validate_record({"end_date": "2026-11-03T14:47:09+00:00"})
    assert result.ok


def test_end_before_start_is_rejected_with_iso_datetimes():
    result = validate_record({"start_date": "2026-05-01T00:00:00+00:00", "end_date": "2026-01-01T00:00:00+00:00"})
    assert not result.ok


def test_missing_region_is_not_an_error():
    result = validate_record({"project_details": "text", "region": ""})
    assert result.ok


def test_compute_active_true_when_end_date_in_future():
    assert compute_active("2099-01-01", run_date=date(2026, 1, 1)) is True


def test_compute_active_false_when_end_date_in_past():
    assert compute_active("2020-01-01", run_date=date(2026, 1, 1)) is False


def test_compute_active_none_when_no_end_date():
    assert compute_active(None) is None
