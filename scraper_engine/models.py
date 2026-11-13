from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FetchMethod = Literal["static", "rendered"]
ExtractionMethod = Literal["selector", "ai_judged", "rule", "literal"]
LoginType = Literal["none", "form", "token", "basic_auth"]


class FieldSpec(BaseModel):
    """How to obtain one field's value for a given site."""

    method: ExtractionMethod
    selector: str | None = None
    attribute: str | None = None  # e.g. "href", "text" (default)
    rule: str | None = None  # e.g. "end_date < run_date -> false" (interpreted by extract.py)
    ai_prompt: str | None = None  # scoped prompt, derived from context.txt at build time
    literal_value: str | None = None  # e.g. source_url is just the page URL


class AuthConfig(BaseModel):
    login_type: LoginType = "none"
    login_url: str | None = None
    username_env: str | None = None
    password_env: str | None = None
    username_selector: str | None = None
    password_selector: str | None = None
    submit_selector: str | None = None


class PaginationConfig(BaseModel):
    type: Literal["none", "next_link", "infinite_scroll"] = "none"
    selector: str | None = None
    max_pages: int = 5


class Skill(BaseModel):
    """Persisted, versioned description of how to scrape one domain."""

    url: str
    domain: str
    created_at: str
    last_verified_at: str
    fetch_method: FetchMethod = "static"
    fields: dict[str, FieldSpec] = Field(default_factory=dict)
    dedup_key_fields: list[str] | None = None  # natural key; None => content hash fallback
    auth: AuthConfig = Field(default_factory=AuthConfig)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    needs_review: bool = False
    needs_review_reason: str | None = None


class ExtractedRecord(BaseModel):
    source_url: str
    domain: str
    data: dict[str, object]
    record_key: str
    key_type: Literal["natural", "hash"]
