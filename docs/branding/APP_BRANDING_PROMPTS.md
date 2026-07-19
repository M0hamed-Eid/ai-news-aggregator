# AI Compass — App Branding Prompts

Prompts for the core brand assets. Today the app has only a text wordmark ("AI Compass") plus a
Bootstrap Icons compass glyph (`bi-compass-fill`) in the navbar — no real logo, favicon, or social
image exists yet. Brand tokens already established in `web/static/css/app.css` and worth staying
consistent with:

- `--app-brand: #4f46e5` (indigo) / `--app-brand-dark: #3730a3`
- `--app-ink: #1a1a2e` (near-black text)
- `--app-bg: #f6f7fb` (pale cool-grey page background)
- Existing motif: a compass, per the app's own name and current icon choice.

## 1. Application logo

> A modern, minimal logo mark for "AI Compass," an AI news intelligence product. A geometric
> compass needle/rose reimagined as a network node — the needle's four points terminate in small
> glowing circular nodes connected by thin lines through the center, suggesting both navigation and
> AI/neural connectivity. Indigo (#4f46e5) on transparent background, flat vector style, no
> gradients needed but soft glow allowed at the center node. Balanced, symmetric, reads clearly at
> both large (hero) and small (32px navbar) sizes. Provide as a standalone mark (usable without the
> wordmark) and, separately, as a horizontal lockup with "AI Compass" set in a clean modern
> geometric sans-serif to its right.

## 2. Favicon

> A simplified, high-contrast version of the AI Compass logo mark (see prompt 1) reduced to its
> most essential shape for legibility at 16×16–48×48px: the compass-needle-as-network-node motif,
> simplified to 2–3 line weights maximum, indigo (#4f46e5) on a white or transparent background.
> No fine detail, no text. Export as a square (1:1) icon suitable for standard favicon sizes
> (16, 32, 48, 180, 512px) and as a maskable PWA icon variant (mark centered within a safe-zone
> circle, solid indigo background fill).

## 3. Social share image (Open Graph / Twitter Card)

> A 1200×630px social preview card for "AI Compass." Dark near-black (#12161b–#1a1a2e range)
> background with a large, softly-glowing version of the compass-needle-as-network-node logo mark
> (indigo #4f46e5, prompt 1) positioned left-of-center, subtle ambient particle/node texture
> scattered faintly in the background suggesting a live data feed. Reserve clean negative space on
> the right third for the app to overlay its own text (tagline/page title) programmatically — do
> not bake in any text yourself. Modern, premium SaaS-product feel, not busy or cluttered.

## 4. Email header image

> A 600×120px (or 1200×240px @2x) email header banner for the "AI Compass" digest email, matching
> the existing email template's white-card-on-light-grey layout (`app/services/email_template.py`).
> Light background (#ffffff or very pale #f7f7f7), small compass-needle-as-network-node logo mark
> (indigo #4f46e5, prompt 1) on the left, generous whitespace, no gradients or dark backgrounds
> (must read cleanly in email clients' light-mode rendering and print reasonably in dark-mode email
> clients too). No text baked in — the email template renders "AI Compass — Daily Digest" as real
> HTML text beside/below it today and should continue to.

## Implementation notes for whoever generates these

- Deliver the logo and favicon as SVG **and** a PNG export (favicon additionally needs literal
  `.ico` for maximum browser-support parity with the app's current zero-favicon state).
- Deliver the social share image and email header as PNG or JPG (not SVG — see the note in
  `docs/branding/SOURCE_ARTWORK_PROMPTS.md` about email/social-crawler SVG support gaps).
- Suggested destinations once generated (not yet wired into code — see
  `SOURCE_ARTWORK_IMPLEMENTATION.md` for the one piece of this that IS wired up today):
  - Logo: `web/static/img/brand/logo.svg`, `web/static/img/brand/logo.png`
  - Favicon: `web/static/img/brand/favicon.ico` (+ standard PNG sizes), referenced from
    `web/templates/base.html`'s `<head>` (currently has no `<link rel="icon">` at all).
  - Social share image: `web/static/img/brand/social-share.png`, referenced via Open Graph/Twitter
    Card `<meta>` tags in `base.html` (none exist today).
  - Email header: `web/static/img/brand/email-header.png`, referenced from
    `app/services/email_template.py`'s header `<tr>` (currently plain text only).
