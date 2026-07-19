# app/services/email_template.py
#
# Renders an EmailDigestResponse as a Medium-style HTML email.
# Kept separate from email_agent.py on purpose: that file generates content
# (LLM calls), this file turns that content into markup — two different jobs.

import html as html_lib
from typing import Optional

from app.agents.email_agent import EmailDigestResponse, RankedArticleDetail

FALLBACK_COLORS = {
    "blog_openai": "#10a37f",
    "blog_anthropic": "#d97757",
    "youtube": "#ff0000",
}
FALLBACK_LABELS = {
    "blog_openai": "OpenAI",
    "blog_anthropic": "Anthropic",
    "youtube": "YouTube",
}

# Mirrors web/apps/catalog/templatetags/source_display.py's _SOURCE_ARTWORK
# map by filename (same source-branding system, extended to email). This is
# a deliberate, precedented small duplication across the Django/pipeline
# ORM boundary — same pattern as FALLBACK_COLORS/FALLBACK_LABELS above,
# which already duplicate naming info that also lives in Django's
# Article.SOURCE_LABELS. NOTE: these ship as .png today (placeholder art,
# see docs/branding/) — most modern webmail (Gmail, Apple Mail) renders
# inline <img src="*.png"> fine, but Outlook desktop's Word-based renderer
# does not. When real generated art replaces these placeholders, prefer a
# .png/.jpg export for the email-facing copies for universal client support.
SOURCE_ARTWORK_FILENAMES = {
    "blog_openai": "blog_openai.png",
    "blog_anthropic": "blog_anthropic.png",
    "arxiv": "arxiv.png",
    "github_release": "github_release.png",
    "youtube": "youtube.png",
    "reddit": "reddit.png",
    "huggingface_model": "huggingface_model.png",
    "government_us": "government_us.png",
    "government_uk": "government_uk.png",
    "government_nist": "government_nist.png",
    "funding_crunchbase": "funding_crunchbase.png",
}


def _esc(text: Optional[str]) -> str:
    return html_lib.escape(text or "")


def _render_media(article: RankedArticleDetail, base_url: Optional[str] = None) -> str:
    """
    Real image if we have one (og:image for articles, YouTube thumbnail for
    videos) — otherwise branded source artwork (if base_url is configured,
    needed since email images must be absolute URLs), else the original
    clean colored banner. Always renders something, never a broken image.
    """
    if article.image_url:
        return (
            f'<img src="{_esc(article.image_url)}" alt="{_esc(article.title)}" '
            f'width="536" style="width:100%; max-width:536px; height:auto; '
            f'display:block; border-radius:8px;" />'
        )
    filename = SOURCE_ARTWORK_FILENAMES.get(article.article_type)
    if base_url and filename:
        artwork_url = f"{base_url}/static/img/sources/{filename}"
        return (
            f'<img src="{_esc(artwork_url)}" alt="{_esc(article.title)}" '
            f'width="536" style="width:100%; max-width:536px; height:180px; '
            f'object-fit:cover; display:block; border-radius:8px;" />'
        )
    color = FALLBACK_COLORS.get(article.article_type, "#4a4a4a")
    label = FALLBACK_LABELS.get(article.article_type, "AI News")
    return (
        f'<div style="width:100%; height:180px; background-color:{color}; '
        f'border-radius:8px; display:table;">'
        f'<div style="display:table-cell; vertical-align:middle; text-align:center; '
        f'color:#ffffff; font-family:Arial, sans-serif; font-size:18px; font-weight:bold; '
        f'letter-spacing:0.5px;">{_esc(label)}</div></div>'
    )


def _render_card(article: RankedArticleDetail, base_url: Optional[str] = None) -> str:
    is_video = article.article_type == "youtube"
    cta_label = "Watch the video" if is_video else "Read the article"
    unit = "watch" if is_video else "read"
    source_label = FALLBACK_LABELS.get(article.article_type, article.article_type)

    return f"""
    <tr>
      <td style="padding:20px 32px;">
        {_render_media(article, base_url)}
        <div style="padding-top:16px; font-family:Arial, sans-serif;">
          <div style="font-size:12px; color:#757575; text-transform:uppercase; letter-spacing:0.5px;">
            {_esc(source_label)} &nbsp;&middot;&nbsp; {article.reading_minutes} min {unit}
          </div>
          <div style="font-size:20px; font-weight:bold; color:#1a1a1a; line-height:26px; padding-top:6px; font-family:Georgia, serif;">
            <a href="{_esc(article.url)}" style="color:#1a1a1a; text-decoration:none;">{_esc(article.title)}</a>
          </div>
          <div style="font-size:15px; color:#4a4a4a; line-height:22px; padding-top:8px;">
            {_esc(article.summary)}
          </div>
          <div style="padding-top:12px;">
            <a href="{_esc(article.url)}" style="font-size:14px; color:#1a8917; font-weight:bold; text-decoration:none; font-family:Arial, sans-serif;">
              {cta_label} &rarr;
            </a>
          </div>
        </div>
      </td>
    </tr>
    <tr><td style="border-bottom:1px solid #f0f0f0;"></td></tr>
    """


def render_email_html(response: EmailDigestResponse, base_url: Optional[str] = None) -> str:
    """
    base_url (optional): the Django site's public base URL, used to build
    absolute source-artwork image URLs (required for email — relative
    static paths don't resolve in a mail client). Pass digest_service.py's
    existing _DJANGO_BASE_URL through at the call site rather than this
    module reading its own os.getenv — keeps one source of truth for that
    value instead of duplicating the env-var lookup. Omit it (default
    None) to keep the original solid-color-banner fallback behavior.
    """
    cards = "".join(_render_card(a, base_url) for a in response.articles)

    return f"""<!DOCTYPE html>
<html>
<body style="margin:0; padding:0; background-color:#f7f7f7;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f7f7f7; padding:24px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:8px;">

          <tr>
            <td style="padding:32px 32px 16px 32px;">
              <div style="font-size:13px; letter-spacing:1px; color:#757575; font-family:Arial, sans-serif; text-transform:uppercase;">AI Compass</div>
              <div style="font-size:30px; font-weight:bold; color:#1a1a1a; padding-top:6px; font-family:Georgia, serif;">Daily Digest</div>
              <div style="border-bottom:1px solid #e6e6e6; margin-top:20px;"></div>
            </td>
          </tr>

          <tr>
            <td style="padding:8px 32px; font-family:Arial, sans-serif;">
              <p style="font-size:15px; line-height:22px; color:#333333; margin:8px 0;">{_esc(response.introduction.greeting)}</p>
              <p style="font-size:15px; line-height:22px; color:#333333; margin:8px 0;">{_esc(response.introduction.introduction)}</p>
              <div style="font-size:12px; letter-spacing:1px; color:#757575; text-transform:uppercase; padding-top:16px;">Today's Highlights</div>
            </td>
          </tr>

          {cards}

          <tr>
            <td style="padding:24px 32px 32px 32px; font-family:Arial, sans-serif;">
              <p style="font-size:12px; color:#9e9e9e;">You're receiving this because you subscribed to the AI Compass daily digest.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""