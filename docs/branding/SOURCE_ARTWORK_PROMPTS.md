# Source Artwork — Image Generation Prompts

One prompt per curated source, for generating the final branded artwork that replaces the
placeholder SVGs currently shipped at `web/static/img/sources/`. See
[SOURCE_ARTWORK_IMPLEMENTATION.md](./SOURCE_ARTWORK_IMPLEMENTATION.md) for how these files are
wired into the app and exactly what to name/where to put the real output.

## Shared visual system (apply to every prompt below)

To read as one consistent family on the Home page (a grid of cards from many different sources
side by side), every image should share:

- **Format**: 16:9 landscape (matches the article-card thumbnail aspect ratio), roughly 1280×720px.
- **Style**: flat modern editorial illustration / geometric abstract — not a photo, not a literal
  logo lockup, not 3D-render clichés. Clean vector-style shapes, generous negative space, soft
  gradients allowed but no heavy drop shadows or bevels.
- **Motif language**: abstract AI/network visual vocabulary — neural-node lattices, flowing data
  lines, soft glow, subtle circuit/grid textures — rendered distinctly per source (see each prompt)
  rather than the same motif recolored.
- **Typography**: none baked into the image except where noted — the app already overlays the
  source name as a text badge on the card, so the artwork itself should stay wordmark-free to avoid
  duplicate/conflicting text.
- **Color**: each source gets its own accent hue (given per prompt below) on a shared dark or
  near-black background family, so the set reads as "one product's brand system, many source
  accents" rather than unrelated stock art.
- **No text, no logos, no watermarks, no borders** — the app renders its own rounded corners and
  card chrome around the image.

## Prompts

### OpenAI (`blog_openai`)
> A flat, modern abstract illustration representing OpenAI's blog, on a near-black background.
> A soft teal-green (#10a37f) glow radiates from a cluster of interconnected nodes forming a
> loose neural lattice, with a few thin curved lines suggesting data flowing outward. Minimalist,
> clean vector style, generous negative space, no text, no logos, 16:9 landscape composition.

### Anthropic (`blog_anthropic`)
> A flat, modern abstract illustration representing Anthropic's blog, on a near-black background.
> A warm terracotta/clay (#d97757) gradient forms soft overlapping rounded shapes like layered
> conversation bubbles or gentle waveforms, suggesting thoughtful dialogue and safety research.
> Minimalist, clean vector style, generous negative space, no text, no logos, 16:9 landscape.

### GitHub Releases (`github_release`)
> A flat, modern abstract illustration representing open-source software releases, on a near-black
> background. A subtle dark slate (#24292f) base with a bright accent thread of small glowing
> nodes connected in a branching tree/graph pattern (like a commit/release history), one node
> highlighted with a soft white-gold glow to suggest a new tagged release. Minimalist, clean
> vector style, no text, no logos, 16:9 landscape.

### Hugging Face (`huggingface_model`)
> A flat, modern abstract illustration representing an open model-sharing community, on a
> near-black background. A warm amber/gold (#ffbf00) glow surrounds a loose cluster of small
> rounded block shapes (representing shared model "packages") linked by thin connecting lines,
> friendly and approachable in tone. Minimalist, clean vector style, no text, no logos, 16:9
> landscape.

### Reddit (`reddit`)
> A flat, modern abstract illustration representing community discussion, on a near-black
> background. A vivid orange-red (#ff4500) glow behind a loose grid of small overlapping speech-
> bubble shapes of varying size, suggesting many simultaneous conversations/threads. Minimalist,
> clean vector style, no text, no logos, 16:9 landscape.

### arXiv (`arxiv`)
> A flat, modern abstract illustration representing academic research papers, on a near-black
> background. A deep maroon-red (#b31b1b) glow behind a stack of thin overlapping rectangular
> "paper" shapes with subtle horizontal line-texture suggesting text, arranged at a slight
> cascading angle. Minimalist, clean vector style, no text, no logos, 16:9 landscape.

### NIST (`government_nist`)
> A flat, modern abstract illustration representing standards and measurement science, on a
> near-black background. A muted violet-purple (#5b2c86) glow behind a precise grid of fine
> measurement-tick lines and a subtle calibrated-dial arc shape, conveying rigor and precision.
> Minimalist, clean vector style, no text, no logos, 16:9 landscape.

### UK Government (`government_uk`)
> A flat, modern abstract illustration representing UK government policy and regulation, on a
> near-black background. A confident blue (#1d70b8) glow behind a simple geometric shield-like
> silhouette built from soft overlapping rounded polygons, formal but not literal/heraldic.
> Minimalist, clean vector style, no text, no logos, 16:9 landscape.

### US Federal Register (`government_us`)
> A flat, modern abstract illustration representing US federal regulatory notices, on a near-black
> background. A deep federal navy (#003a63) glow behind a subtle radiating-seal motif built from
> soft concentric arcs (not a literal eagle/seal), formal and institutional in tone. Minimalist,
> clean vector style, no text, no logos, 16:9 landscape.

### Crunchbase — AI funding news (`funding_crunchbase`)
> A flat, modern abstract illustration representing startup funding and investment, on a
> near-black background. A bright cobalt blue (#146aff) glow behind an upward-trending arrangement
> of small rounded bar/node shapes connected by thin ascending lines, suggesting growth and
> momentum. Minimalist, clean vector style, no text, no logos, 16:9 landscape.

### YouTube (`youtube`)
> A flat, modern abstract illustration representing video content, on a near-black background. A
> vivid red (#ff0000) glow behind a soft rounded play-triangle shape at the center, surrounded by
> a few thin concentric arcs suggesting a video signal radiating outward. Minimalist, clean vector
> style, no text, no logos, 16:9 landscape. (Used only for source-catalog/branding surfaces — real
> YouTube video thumbnails are used everywhere content itself is shown, per the app's existing
> behavior.)

### Default / custom user-submitted source (`_default`)
> A flat, modern abstract illustration representing a generic linked content feed, on a near-black
> background. A neutral indigo (#4f46e5) glow — matching AI Compass's own brand color — behind a
> simple radiating "signal" motif: a small circle with 2–3 soft concentric arcs suggesting an RSS/
> feed broadcast. Minimalist, clean vector style, no text, no logos, 16:9 landscape. Should read as
> "a generic, still-polished placeholder," not tied to any specific real brand.
