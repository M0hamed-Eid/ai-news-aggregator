"""
Display helpers for the news app.

The pipeline stores raw scraped content in `articles.content`, which for some
sources includes a metadata block at the top (YAML-style `--- ... ---`
frontmatter and stray `meta-og:` / `canonical:` / `twitter:` lines). We strip
that noise and render the real body as sanitized HTML — purely at display time,
without modifying the pipeline or the stored data.
"""
import re

from django.utils.html import escape
from django.utils.html import linebreaks as _linebreaks
from django.utils.safestring import mark_safe

try:
    import bleach
    import markdown as _markdown

    _HAS_MARKDOWN = True
except Exception:  # markdown/bleach not installed — fall back to plain text
    _HAS_MARKDOWN = False

# A leading frontmatter block: ---\n ... \n---
_FRONTMATTER = re.compile(r"\A\s*---\s*\n.*?\n---\s*\n", re.DOTALL)

# Stray metadata lines anywhere in the text.
_META_LINE = re.compile(
    r"^\s*(?:meta-[\w:.\-]+|canonical|og:[\w:]+|twitter:[\w:]+|robots|viewport|title)\s*:.*$",
    re.IGNORECASE | re.MULTILINE,
)

_ALLOWED_TAGS = [
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "b", "i", "u", "a",
    "blockquote", "code", "pre", "img", "table", "thead",
    "tbody", "tr", "th", "td",
]
_ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title"],
}


def _strip_noise(text: str) -> str:
    text = _FRONTMATTER.sub("", text, count=1)
    text = _META_LINE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_body(content: str):
    """Return clean, safe HTML for an article/transcript body."""
    if not content:
        return mark_safe("")

    cleaned = _strip_noise(content)
    if not cleaned:
        return mark_safe("")

    if _HAS_MARKDOWN:
        html = _markdown.markdown(cleaned, extensions=["extra", "sane_lists"])
        safe = bleach.clean(
            html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True
        )
        return mark_safe(safe)

    # Fallback: escape then preserve paragraphs/line breaks.
    return mark_safe(_linebreaks(escape(cleaned)))
