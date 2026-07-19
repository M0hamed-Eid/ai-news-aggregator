# Source Artwork — Implementation Reference

How per-source branded artwork is wired into AI Compass today, and how to upgrade the current
placeholder art to real generated art (see `SOURCE_ARTWORK_PROMPTS.md`) without touching any code.

## Where the assets live

```
web/static/img/sources/
    blog_openai.svg
    blog_anthropic.svg
    arxiv.svg
    github_release.svg
    youtube.svg
    reddit.svg
    huggingface_model.svg
    government_us.svg
    government_uk.svg
    government_nist.svg
    funding_crunchbase.svg
    _default.svg          ← used for any source not explicitly listed above
```

Filenames match each curated `Source.key` from `app/database/seed_sources.py` exactly. This is a
plain Django static-files directory (`STATICFILES_DIRS` in `web/config/settings/base.py`) — not a
database column and not a media/uploads directory (this project deliberately has neither; see
`web/config/settings/prod.py`'s own comment on that). Swapping an image is just replacing the file
at the same path; no migration, no admin UI, no code change.

## How the app resolves "this article's source → its artwork"

`Article.source` (and `YoutubeVideo.source`) is a plain string, not a foreign key — it matches
`Source.key` only by convention (same pattern the existing `Article.SOURCE_LABELS` display-name
dict already relies on). `web/apps/catalog/templatetags/source_display.py` defines the
`source_artwork` template filter: a small in-file dict from key → static path, with any unmapped
key (i.e. every dynamic, user-submitted custom source) falling through to `_default.svg`. No
database query — it's a pure static lookup, evaluated per-template-render.

Used in:
- `web/templates/components/_article_card.html` — third-tier fallback: a real per-article
  `image_url` (when the pipeline scraped one) wins first; otherwise the source's branded artwork.
  Video cards are untouched — `_video_card.html` always uses the real YouTube thumbnail
  (`YoutubeVideo.thumbnail_url`, derived from `video_id`), per the requirement that YouTube
  content keep using real thumbnails.
- `web/templates/onboarding/sources.html` — a small 28×28 icon next to each curated source's name
  in the "Individual sources" catalog table (this is what makes `youtube.svg` load-bearing, since
  `Article.source` never actually equals `"youtube"` — video content lives in a separate table).

## Email reuse (optional, degrades gracefully)

`app/services/email_template.py` (pipeline-side, SQLAlchemy — a separate Python process from
Django) has its own small `SOURCE_ARTWORK_FILENAMES` dict mirroring the same 11 keys. When
`render_email_html(response, base_url=...)` is called with a real `base_url` (the digest phase in
`run_pipeline.py` passes `digest_service._DJANGO_BASE_URL` through — no new env var), the digest
email's per-item fallback banner renders a real `<img>` pointing at
`{base_url}/static/img/sources/{filename}` instead of the original solid-color-banner-with-text.
Omitting `base_url` (or hitting an unmapped source) preserves the exact original color-banner
behavior — nothing regresses if this is left unconfigured.

**Known caveat:** the shipped placeholder files are `.svg`. Most modern webmail (Gmail, Apple Mail)
renders inline `<img src="*.svg">` fine; Outlook's desktop (Word-based) renderer generally does
not. This is fine for now since these are stand-in placeholders — see the next section.

## Upgrading to real generated art

1. Generate images from the prompts in `SOURCE_ARTWORK_PROMPTS.md` (one per source, plus the
   default and the four `APP_BRANDING_PROMPTS.md` assets).
2. For anything that will render in email, export as `.png` or `.jpg`, not `.svg` (see the caveat
   above).
3. Drop the files in at the exact same paths/filenames listed above (or update the two filename
   dicts — `source_display.py`'s `_SOURCE_ARTWORK` and `email_template.py`'s
   `SOURCE_ARTWORK_FILENAMES` — if you change the extension from `.svg` to `.png`, since both
   currently hardcode the `.svg` extension per file).
4. No other code changes needed — both the web templates and the email template read from these
   two dicts, not from a hardcoded extension assumption anywhere else.
