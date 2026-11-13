from scraper_engine.dedup import compute_record_key


def test_natural_key_used_when_fields_present():
    data = {"source_url": "https://x.org/a", "project_details": "p"}
    key, key_type = compute_record_key(data, ["source_url"])
    assert key_type == "natural"
    assert key == "https://x.org/a"


def test_falls_back_to_hash_when_natural_key_fields_missing():
    data = {"source_url": "", "project_details": "p"}
    key, key_type = compute_record_key(data, ["source_url"])
    assert key_type == "hash"
    assert len(key) == 64


def test_falls_back_to_hash_when_no_dedup_fields_configured():
    data = {"project_details": "p"}
    key, key_type = compute_record_key(data, None)
    assert key_type == "hash"


def test_hash_is_stable_for_same_content_regardless_of_key_order():
    data_a = {"a": 1, "b": 2}
    data_b = {"b": 2, "a": 1}
    key_a, _ = compute_record_key(data_a, None)
    key_b, _ = compute_record_key(data_b, None)
    assert key_a == key_b


def test_hash_changes_when_content_changes():
    key_a, _ = compute_record_key({"a": 1}, None)
    key_b, _ = compute_record_key({"a": 2}, None)
    assert key_a != key_b
