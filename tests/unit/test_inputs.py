from scraper_engine.inputs import load_context, load_urls


def test_load_urls_skips_blank_and_comment_lines(tmp_path):
    p = tmp_path / "urls.txt"
    p.write_text("# comment\nhttps://a.org\n\nhttps://b.org\n", encoding="utf-8")
    assert load_urls(p) == ["https://a.org", "https://b.org"]


def test_load_context_strips_whitespace(tmp_path):
    p = tmp_path / "context.txt"
    p.write_text("  some context  \n", encoding="utf-8")
    assert load_context(p) == "some context"
