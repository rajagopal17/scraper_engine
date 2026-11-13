from __future__ import annotations

import hashlib
import json


def compute_record_key(data: dict, dedup_key_fields: list[str] | None) -> tuple[str, str]:
    """Return (record_key, key_type).

    Uses a natural key built from the skill's designated identity fields when
    available and non-empty; otherwise falls back to a content hash of the
    full record (any change to the content is then treated as a new record).
    """
    if dedup_key_fields:
        values = [str(data.get(f, "")).strip() for f in dedup_key_fields]
        if all(values):
            natural_key = "|".join(values)
            return natural_key, "natural"

    canonical = json.dumps(data, sort_keys=True, default=str)
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return content_hash, "hash"
