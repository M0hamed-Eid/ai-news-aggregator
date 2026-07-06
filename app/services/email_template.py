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


def _esc(text: Optional[str]) -> str:
    return html_lib.escape(text or "")


def _render_media(article: RankedArticleDetail) -> str:
    """
    Real image if we have one (og:image for articles, YouTube thumbnail for
    videos) — otherwise a clean colored banner. No AI generation, no image
    hosting needed, always renders something.
    """
    if article.image_url:
        return (
            f'<img src="{_esc(article.image_url)}" alt="{_esc(article.title)}" '
            f'width="536" style="width:100%; max-width:536px; height:auto; '
            f'display:block; border-radius:8px;" />'
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


def _render_card(article: RankedArticleDetail) -> str:
    is_video = article.article_type == "youtube"
    cta_label = "Watch the video" if is_video else "Read the article"
    unit = "watch" if is_video else "read"
    source_label = FALLBACK_LABELS.get(article.article_type, article.article_type)

    return f"""
    <tr>
      <td style="padding:20px 32px;">
        {_render_media(article)}
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


def render_email_html(response: EmailDigestResponse) -> str:
    cards = "".join(_render_card(a) for a in response.articles)

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