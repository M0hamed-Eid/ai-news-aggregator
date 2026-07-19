# Static-path lookup for curated Source.key -> its branded placeholder
# artwork. Mirrors the plain in-file dict precedent already used by
# Article.SOURCE_LABELS (apps/catalog/models.py) and email_template.py's
# FALLBACK_COLORS (app/services/email_template.py, pipeline side) — a
# static, code-cadence lookup table, not runtime config or a DB column.
#
# Article.source is a plain string (not a FK), matching Source.key only
# by convention, so this filter needs zero DB query. Any key NOT in the
# map (every dynamic user-submitted custom source) falls back to the
# default placeholder — exactly the "custom sources use the default
# placeholder" requirement, with no extra branching needed at call sites.
from django import template
from django.templatetags.static import static as static_url

register = template.Library()

_SOURCE_ARTWORK = {
    "blog_openai": "img/sources/blog_openai.png",
    "blog_anthropic": "img/sources/blog_anthropic.png",
    "arxiv": "img/sources/arxiv.png",
    "github_release": "img/sources/github_release.png",
    "youtube": "img/sources/youtube.png",
    "reddit": "img/sources/reddit.png",
    "huggingface_model": "img/sources/huggingface_model.png",
    "government_us": "img/sources/government_us.png",
    "government_uk": "img/sources/government_uk.png",
    "government_nist": "img/sources/government_nist.png",
    "funding_crunchbase": "img/sources/funding_crunchbase.png",
}
_DEFAULT_ARTWORK = "img/sources/_default.png"


@register.filter
def source_artwork(source_key):
    """
    Resolve a Source.key / Article.source string to its branded
    placeholder artwork's static URL. Unknown keys (dynamic user-
    submitted sources) resolve to the shared default placeholder.
    """
    relative_path = _SOURCE_ARTWORK.get(source_key, _DEFAULT_ARTWORK)
    return static_url(relative_path)
