# AI Compass — User Guide

*A complete guide to using AI Compass: your personalized AI news, research, and release tracker.*

> This guide covers every page, button, and workflow available in the product today, written for end users — no technical background required. It was compiled by walking through the live application page by page.

---

## Table of Contents

1. [What is AI Compass?](#1-what-is-ai-compass)
2. [User Roles & Access Levels](#2-user-roles--access-levels)
3. [Getting Started: Account Basics](#3-getting-started-account-basics)
4. [The Free User Journey](#4-the-free-user-journey)
5. [The Pro User Journey](#5-the-pro-user-journey)
6. [Source Management](#6-source-management)
7. [Complete Navigation Map](#7-complete-navigation-map)
8. [End-to-End User Scenarios](#8-end-to-end-user-scenarios)
9. [Quick Reference: Free vs. Pro](#9-quick-reference-free-vs-pro)

---

## 1. What is AI Compass?

AI Compass is a personalized AI news aggregator. It continuously collects articles, research papers, model releases, and videos from **11 sources** — including OpenAI's blog, Anthropic's blog, arXiv, GitHub Releases, Reddit, Hugging Face, YouTube, UK and US government feeds, NIST, and Crunchbase News — and organizes them into:

- A public, browsable stream of everything that's been collected (**Home**)
- A ranked, personalized feed built around your interests, persona, and the sources you follow (**My Feed**)
- Topic and people tracking, trend detection, and a weekly AI-generated (but fully cited) briefing on what's trending

You can use the product anonymously to browse, or create a free account to personalize it, save items, and get an email digest. A paid **Pro** tier unlocks higher usage limits and a few advanced features.

---

## 2. User Roles & Access Levels

AI Compass has four effective access levels. There is no separate "sign-up plan" to choose — every new account starts as **Free**, and everyone (including anonymous visitors) sees the same core product; the differences are about *personalization, limits, and a few advanced features*.

| Role | How you get it | Can access | Cannot access / Restricted |
|---|---|---|---|
| **Visitor** (not logged in) | Default — no account needed | **Home** (public news stream with search/filters) and **Search** (public, keyword or semantic) | Everything else — My Feed, Sources, People, Insights, Library, News list/detail pages, entity/person profiles all require an account. Clicking Save/Hide/Follow while logged out redirects you to the login page. |
| **Free member** | Sign up with an email + password | Everything a Visitor sees, plus: My Feed, Sources, People, Insights *(locked upsell page)*, Library, article/video detail pages, saving, hiding, following, personalization settings, digest emails | • Up to **3** self-submitted custom sources<br>• Up to **20** total follows (topics + people/entities)<br>• No chapter breakdowns on long-form videos (20+ minutes)<br>• No weekly Insights briefing (page shows an upgrade prompt instead of content) |
| **Pro member** | Upgrade via the Pricing page (paid subscription) | Everything Free members see, with three limits lifted and one feature unlocked (see [§5](#5-the-pro-user-journey) and [§9](#9-quick-reference-free-vs-pro)) | Nothing product-wide is hidden from Pro members |
| **Staff / Admin** | Granted internally (not self-service — set by whoever manages the deployment) | Everything a Pro member sees, plus a read-only **Ops Dashboard** (`/ops/`) showing the health of every content source, and access to the Django administrative site for account management | This is an operational role, not a content-personalization role — staff status doesn't change what content you're recommended |

A quick way to think about it: **being logged in** unlocks the personalized product; **being Pro** raises three specific ceilings (custom sources, follows, long-video chapters) and unlocks one specific feature (the weekly trend briefing); **being staff** adds an internal monitoring page, nothing consumer-facing.

---

## 3. Getting Started: Account Basics

### 3.1 Creating an account

**Location:** Click **Sign up** in the top-right corner of any page, or go directly to the registration page.

**Steps:**
1. Enter your **Email**.
2. Optionally enter your **First name**.
3. Choose a **Password** and repeat it in **Password confirmation**.
4. Click **Sign up**.

**Result:**
- Your account is created and you're **logged in immediately** — there's no separate "check your email before you can log in" step.
- A verification email is sent to your address (see §3.3 below). If it can't be sent for some reason, you'll see a warning that you can resend it later.
- You're taken straight into the **3-step onboarding wizard** (see §4.1) to set up your persona, interests, and starting sources.

If you're already logged in and visit the sign-up page, you're simply redirected to Home.

### 3.2 Logging in and out

**Log in — Location:** Click **Log in** (or go to `/accounts/login/`).

**Steps:**
1. Enter your **Email** and **Password**.
2. Click **Log in**.
3. Forgot your password? Click the **Forgot password?** link next to the password field (see §3.4).

**Result:** You're taken to your intended destination (or Home).

**Rate limiting (security):** If you get the password wrong repeatedly, the login form will start refusing attempts. Specifically, **more than 5 attempts within 5 minutes** — counted separately by your IP address and by the email address you're typing — triggers a message: *"Too many login attempts. Please wait a few minutes and try again."* This resets automatically 5 minutes after your first attempt in that window. This applies even if some of those attempts had the correct password, so don't rapid-fire retry — wait a few minutes.

**Log out — Location:** Open the account menu (your name/avatar, top-right) → **Log out**.

### 3.3 Email verification

**Location:** A banner appears at the top of every page — *"Please verify your email address."* with a **Resend verification email** button — until you verify.

**Important:** Email verification is **optional for normal use**. You can browse, personalize, save, follow, and use every feature of the site while unverified. The **only** place it's actually required is **before upgrading to Pro** — Stripe checkout will block you with a message asking you to verify first.

**Steps:**
1. Open the verification email sent to you (subject: *"Verify your AI Compass email"*).
2. Click the verification link.
3. You'll land back on the site with a confirmation: *"Your email is verified."*

If your link doesn't work (expired or already used), you'll see: *"That verification link is invalid or has already been used."* — click **Resend verification email** from the banner (or your Profile page) to get a fresh one.

### 3.4 Resetting your password

**Location:** **Forgot password?** link on the login page, or go directly to `/accounts/password_reset/`.

**Step-by-step:**
1. **Reset your password page** — enter your account **Email**, click **Send reset link**.
2. **Check your email page** — confirms: *"If an account exists for that address, we've sent a link to reset your password."* (This wording is intentional and doesn't confirm whether the email is registered, for privacy.)
3. **Email received** — subject *"Reset your AI Compass password"*, containing a one-time reset link.
4. **Set a new password page** — click the emailed link, enter a **New password** and **New password confirmation**, click **Set password**. If the link has expired or was already used, you'll see **"Link invalid or expired"** with a button to **Request a new link**.
5. **Password reset page** — confirms *"Your password has been changed successfully."* with a **Log in** button.

---

## 4. The Free User Journey

This section walks through the complete experience of a signed-up (Free) member, from first login to daily use.

### 4.1 Onboarding wizard (shown once, right after signup)

**Location:** Automatically shown right after you create your account (`/onboarding/`). Fully optional/skippable — nothing in the app is locked behind finishing it.

It's a 3-step wizard:

| Step | Question | What you choose |
|---|---|---|
| 1 | **"Who are you?"** *(Optional — helps us frame summaries at the right level)* | One persona: Student, Researcher, Engineer / Developer, Product Manager, Executive / Leader, Founder / Entrepreneur, or Hobbyist / Enthusiast |
| 2 | **"What are you into?"** *(Pick as many as you like — this drives your Feed ranking)* | Any number of interests from 4 groups: **Core AI** (Large Language Models, AI Agents, Open Source Models, NLP, Machine Learning Research, RAG & Vector Databases, Computer Vision, Reinforcement Learning, Multimodal AI), **Policy** (AI Safety & Alignment, AI Policy & Regulation), **Applications** (Robotics, MLOps & Infrastructure, Developer Tools), **Business** (Startups & Funding) |
| 3 | **"Any sources to skip?"** *(Everything is included by default)* | Uncheck any source you'd rather not see in your feed/digest |

Each step has a **Skip this step** button (moves on without saving that step) and a **Next →** / **Finish ✓** button (saves and moves on). Below the wizard card, there's always an escape hatch: **"I'll finish this later — take me to the app"** — this takes you straight to My Feed and leaves onboarding incomplete (you won't be forced back into it, but the "Onboarding" link stays in your account menu as a reminder).

Finishing the last step shows: *"You're all set! Your feed will personalize as digests run."* and takes you to **My Feed**. Once completed, the wizard won't show itself again — revisiting `/onboarding/` just redirects you to the Preferences page.

### 4.2 Home page

**Location:** `/` — the default landing page, public (works whether logged in or not).

**What's on it:**
- A hero banner: *"What's happening in AI right now"* — for anonymous visitors, this includes **Get your personalized feed** and **Log in** buttons; logged-in users see **Go to My Feed** instead.
- **Trending** — a row of pills for topics/entities currently spiking in mention volume (e.g., "3.2x" above their normal baseline), plus "hot cluster" 🔥 pills for stories multiple sources are covering at once. If nothing is trending, you'll see: *"Nothing is trending right now."*
- **Featured** — up to 3 larger cards for recent items that have an image.
- **Latest** — the full, paginated stream of everything collected, newest first.

**Filters available (all on one form):**
- **Search box** — free-text search across titles, summaries, and authors
- **Category** dropdown — Research, Open Source, Product / Model Databases, Developer Communities, Government, Funding, Media
- **Source** dropdown — every active source (Anthropic Blog, OpenAI Blog, arXiv, GitHub Releases, Hugging Face, Reddit, UK Government, US Federal Register, NIST News, Crunchbase News, YouTube, plus any custom sources you or others have added)
- **Topic** dropdown — one of 27 topic tags (a superset of the onboarding interests, used for content classification)
- **Date** picker — only show items from a given date onward
- **Search** button to apply, **Clear filters** to reset (only shown when a filter is active)

Results are paginated, 12 items per page. Note: privately-submitted sources that haven't been made public never appear on Home, even to the person who submitted them — Home is always the "everyone sees the same public stream" view.

### 4.3 My Feed (your personalized feed)

**Location:** `/feed/` — nav link **My Feed**. Requires login.

**What it is:** Your personal, ranked version of the content stream, built from your interests, persona, follows, and browsing behavior. Each item shows a rank number and, usually, a **"Recommended for you"** box explaining *why* it was picked — e.g., *"Recommended because it matches your interest in robotics, and a high-quality item"* or *"Selected based on overall relevance to your profile."*

**Brand-new accounts:** until your first personalized ranking has been computed (this runs on a schedule, not instantly), you'll see a banner: *"Your personalized ranking will appear after your first digest run. Showing the newest content instead, already filtered by your source/category exclusions."* — so the feed is never empty on day one, it just isn't ranked yet.

**Controls:** A **Tune my feed** button takes you straight to the Preferences page. There's no in-page search/filter — ranking order is the whole point of this page.

**Empty feed:** If truly nothing matches yet: *"Your feed is empty — Once new content matching your interests is ingested, it will show up here."* with a **Browse latest news** button back to Home.

### 4.4 Search

**Location:** `/search/` — nav link **Search**. Public (no login needed).

Type a natural-language query — the placeholder suggests things like *"agentic coding tools"* or *"llm quantization techniques"*. Search understands meaning, not just exact keywords ("semantic search") when it's available. If the meaning-based search engine is temporarily unavailable, the page automatically falls back to a plain keyword search and shows a banner: *"Semantic search is temporarily unavailable. Showing keyword results instead — the meaning-based search will be back shortly."* You'll still get results either way, just less precisely matched during a fallback.

Results are paginated (12/page) and show the same cards as Home, with Save/Hide buttons and topic badges — but no personalized ranking (Search is not personalized to you).

### 4.5 Article & video detail pages

**Location:** Click **Read more** / **Watch** on any card, or **Read the full article** / **Watch on YouTube** buttons on the detail page itself (opens the original source in a new tab). Requires login.

**What's shown:**
- Source, publish date, and (when available) a **content category** badge and a **Technical depth** gauge (1–5)
- Title, author, and tag chips
- **Topic chips** you can click to follow that topic
- A **Summary**
- A **"Why it matters"** box explaining the significance
- **"Mentioned:"** chips for every person/company/model/technology named in the piece — click to follow any of them
- A **"Recommended for you"** box, if this item is part of your personalized feed, showing the same reasoning text from My Feed
- A **Related** section — other coverage of the same story from different sources (or, if not yet grouped with anything, other recent items from the same source)

Opening a detail page automatically marks that item as "read" in your Library — no extra action needed.

**Videos specifically:** long videos (20 minutes or more) can have a **Chapters** section — see §5.2, this is the one Pro-gated content feature.

### 4.6 Saving, hiding, and your Library

Every article/video card — on Home, My Feed, Search, and detail pages — has two small icon buttons:

| Feature | Location | Steps | Result |
|---|---|---|---|
| **Save** | Bookmark icon on any card | Click it | Instantly bookmarks the item (icon fills in) — no page reload. Click again to remove it. |
| **Hide ("Show less like this")** | Eye-slash icon on any card | Click it | The card disappears immediately from your current view, and the app notes it as a "less like this" signal for future recommendations |

**Library page** — `/behavior/library/`, nav link **Library**. Requires login. Two sections:
- **Saved** — everything you've bookmarked, most recent first. Unsave the same way you saved — click the (now filled) bookmark icon. Empty state: *"Nothing saved yet — Use the bookmark icon on any card to save it for later."*
- **Read history** — every article/video you've opened, most recent first, filled in automatically as you browse (no manual action needed). Empty state: *"No read history yet — Articles and videos you open will show up here."*

No filters beyond the Saved/Read-history split, and no limit on how many items you can save.

### 4.7 Following topics and people

**Location:** "Follow" buttons/chips appear on: topic and "Mentioned" chips on article/video detail pages, the People list, and entity/person profile pages.

**Steps:** Click a chip once to follow (icon changes from `+` to a checkmark); click again to unfollow.

**Free-tier limit:** Free accounts can follow **up to 20** things total (topics and people/entities combined). Trying to follow a 21st shows: *"Free accounts can follow up to 20 — upgrade to Pro for unlimited."* Un-following is always unrestricted, even at the cap.

**People page** — `/news/people/`, nav link **People**. Requires login. A searchable list of every tracked person; each has a compact follow toggle. Selecting a name opens their profile.

**Entity / person profile pages** — `/entity/<id>/`. Requires login. Shows:
- A 90-day **mention sparkline** (a small bar chart — taller/brighter bars mean more mentions that day, with days that were actually "trending" highlighted)
- **"Their own output"** (for people specifically) — their own blog posts, YouTube videos, GitHub activity, or Substack posts, when we've registered that footprint
- **"Mentions"** — up to 12 recent items that reference this person/company/model/technology
- **"Related"** — other entities that frequently appear alongside this one

### 4.8 Personalizing your account

Two different pages control personalization — think of it as "what you're interested in" (Preferences) vs. "how content should be ranked and delivered" (Profile).

**Preferences — `/onboarding/preferences/`** (reachable from the account menu, or the **Tune my feed** / **Manage interests** buttons):
Check or uncheck any of the 15 interest tags (same list as onboarding step 2), grouped by category. Click **Save interests**. Confirmation: *"Your interests were updated — they'll shape your next feed ranking."*

**Profile — `/accounts/profile/`** (account menu → **Profile**):
- **Name**, **Bio** (both editable); **Email** is shown but locked — contact support to change it.
- **Persona** dropdown (same list as onboarding step 1).
- **Digest frequency** — Daily or Weekly.
- **Pause my digest emails** checkbox — stop the emails while still seeing everything in My Feed.
- **Ranking preferences** section — these directly shape how My Feed and your digest are ranked, not just display:
  - **Technical level** — Beginner (lighter, more introductory content) / Intermediate (a mix of depth) / Advanced (deep technical content)
  - **Items per feed refresh** — a number between 5 and 50
  - **Article vs. video mix** — Balanced / Prefer articles / Prefer videos
  - **Research vs. industry lean** — Balanced / Research-leaning / Industry-leaning
  - **Reading-time budget (minutes)** — an optional cap (1–120 minutes); items well over this are gently deprioritized, never excluded outright
- Click **Save changes**. Confirmation: *"Profile updated."*

A sidebar on the Profile page also shows an "at a glance" summary (digests received, interests followed, onboarding status), your top interests, and your 5 most-engaged-with sources (derived automatically from your activity — not editable there directly).

### 4.9 Digest emails and notifications

Your only "notification" surface today is the **digest email** — a periodic summary of your ranked content, sent Daily or Weekly per your Profile setting, or paused entirely with the **Pause my digest emails** checkbox. There is no separate push-notification or in-app-alert system.

### 4.10 What's tracked, and why (personalization, in plain terms)

While you're signed in and browsing, the app quietly notices a few things to make future recommendations better — no extra effort needed on your part:

- Which items you scroll past and which you actually click into
- Roughly how long you spend on a page and how far you scroll
- What you explicitly **Save**, **Hide**, and **Follow** — these count the most
- What you search for
- Which articles/videos you click from a digest email

None of this happens while you're logged out. Detailed raw activity logs (views, clicks, dwell time) are automatically deleted after about 90 days; your saved items, hidden items, and read history are kept until you change them yourself.

### 4.11 Free-tier limitations, at a glance

| Limit | Value | What happens when you hit it |
|---|---|---|
| Custom sources you can submit | 3 | *"Free accounts can add up to 3 custom sources — upgrade to Pro for unlimited."* |
| Total follows (topics + people/entities) | 20 | *"Free accounts can follow up to 20 — upgrade to Pro for unlimited."* |
| Long-video (20+ min) chapter breakdowns | Not available | A locked card on the video page inviting you to upgrade — the rest of the page works normally |
| Weekly Insights trend briefing | Not available | The Insights page loads normally but shows an upgrade prompt instead of the report |

Every limit shows a clear, friendly message rather than blocking the page outright — you always know exactly why something is unavailable and what unlocks it.

---

## 5. The Pro User Journey

### 5.1 Upgrading to Pro

**Location:** **Pricing** page (`/pricing/`, in the top nav for everyone) or the **Upgrade to Pro** button on the Billing page.

**Steps:**
1. Go to **Pricing**. You'll see **Free** and **Pro** plan cards side by side.
2. If you're logged out, the Pro card shows **Log in to upgrade** — log in first, then come back.
3. If you're logged in but haven't verified your email, upgrading will be blocked with: *"Please verify your email before upgrading — check the banner above or resend it from your profile."* (see §3.3).
4. Click **Upgrade to Pro**. You're taken to a secure, Stripe-hosted checkout page (not part of the AI Compass site itself) to enter payment details and confirm your subscription.
5. After payment, you're brought back to AI Compass with a message: *"Thanks! Your upgrade is processing — this usually takes just a few seconds."*
6. Your account is switched to Pro automatically in the background within a few seconds of payment confirming — no manual step needed. Refresh the Billing page to see your new plan reflected.

If you cancel out of checkout instead of completing it, you'll land back on Pricing with: *"Checkout canceled — no changes were made."*

### 5.2 What changes once you're Pro

| Free limit | As a Pro member |
|---|---|
| 3 custom sources | **Unlimited** custom sources |
| 20 follows | **Unlimited** follows |
| No chapters on long videos | **Chapters** section unlocked on every video 20+ minutes long |
| No weekly Insights briefing | Full access to the **weekly grounded trend briefing**, on-site and by email |

**Chaptered video summaries — Video Detail page:** For any video 20 minutes or longer, Pro members see a **Chapters** heading with a list of chapters, each showing a title, a clickable timestamp (e.g. ▶ 12:45) that jumps straight to that point in the YouTube video, and a short summary of what happens in that chapter. This makes long technical talks and interviews skimmable without watching the whole thing. (Under 20 minutes, no video — Free or Pro — gets a chapters section; there's nothing to chapter.)

**Weekly Insights — `/insights/` page, nav link "Insights":** A grounded, cited briefing on what's trending in AI. Every claim in the report links back to the real articles/videos it's based on — nothing is invented. Each week you'll see a headline and a short write-up per trend, with **Sources:** links you can click to jump straight to the original coverage. This same briefing is **automatically emailed** to every active Pro member (no separate opt-in needed) shortly after it's generated each week. If nothing trended strongly enough in a given week, you'll simply see: *"No insights yet — Nothing trended strongly enough last week to write a grounded briefing about."*

### 5.3 Managing your subscription

**Location:** **Billing** page (`/accounts/billing/`, from the account menu).

Shows your current plan (Free/Pro badge), and for Pro members either your renewal date or "Active subscription." A **Usage** panel shows your custom sources used, follows used, and total digests received (unlimited items show as "(unlimited)" for Pro).

- **Pro members:** click **Manage subscription** to open Stripe's secure Billing Portal, where you can update your payment method or cancel your subscription. Canceling doesn't happen on the AI Compass site directly — it's handled by Stripe on your behalf, and your account automatically reverts to Free once the current billing period ends (you keep Pro access until then).
- **Free members:** click **Upgrade to Pro** to go to Pricing.

---

## 6. Source Management

### 6.1 What is a "source"?

A source is an origin AI Compass pulls content from — a blog, an RSS/Atom feed, a research feed, a video channel, etc. There are two kinds:

- **Curated (global) sources** — the 11 built-in sources set up by the AI Compass team (OpenAI Blog, Anthropic Blog, arXiv, GitHub Releases, Hugging Face Models, Reddit, UK Government, US Federal Register, NIST News, Crunchbase News, YouTube). These feed into everyone's Home page and, unless you exclude them, your own feed and digest.
- **Custom (user-submitted) sources** — any AI-relevant RSS/Atom feed you or another member adds yourself. These are private and subscription-based: they never appear on the public Home page (even to the person who added them) — only subscribers see that content in their personal feed and digest.

### 6.2 Adding your own source

**Location:** **Sources** page (`/onboarding/sources/`, nav link **Sources**) → **"Add your own source"** section at the top.

**Steps:**
1. Enter the **Feed URL (RSS/Atom)**.
2. Enter a **Display name** for it.
3. Choose a **Category**: Research, Open Source, Product / Model Databases, Developer Communities, Government, Funding, or Media.
4. Click the submit button (plus icon).

**Result:** The feed is checked automatically to confirm it's genuinely AI-relevant (this takes a few seconds — up to about 20). You'll see one of these outcomes as a banner message:
- **Accepted** — the feed is clearly AI-related and has been added; you're automatically subscribed.
- **Accepted (low confidence)** — added, but the AI-relevance check wasn't fully certain.
- **Rejected** — the feed doesn't look AI-focused, with a reason given.
- If the exact same feed URL was already submitted by someone else, you're simply subscribed to the existing source rather than creating a duplicate.

If validation can't complete in time, you'll see: *"Couldn't validate that feed right now — please try again in a moment."* — just try again.

**Limitations:**
- **Free members:** up to **3** custom sources. At the limit: *"Free accounts can add up to 3 custom sources — upgrade to Pro for unlimited."*
- **Pro members:** unlimited.

Sources you've personally submitted appear in a **"Sources you've submitted"** table further down the page, with their category and status (**Accepted**, **Accepted (low confidence)**, **Rejected**, or **Pending**).

### 6.3 Subscribing and unsubscribing

Submitting a new source automatically subscribes you to it. Your active subscriptions appear in a **"Your subscriptions"** section as chips — each with an **×** button to unsubscribe. Unsubscribing stops that source's content from feeding your personal feed/digest; it doesn't delete the source itself if others are still subscribed to it.

### 6.4 Managing (including/excluding) curated sources

Further down the Sources page:
1. Optionally search by name or filter by **Category** to narrow the list.
2. **Categories** section — checkbox chips for all 7 categories; uncheck one to exclude everything in that category from your feed/digest.
3. **Individual sources** table — every curated source, checked (included) by default; uncheck any you don't want to see.
4. Click **Save source preferences**.

Changes only affect the sources currently shown by your search/filter — if you're viewing a filtered subset, saving won't silently change sources outside that view. Confirmation: *"Your source preferences were updated."* Note: changes apply on the next personalization run, not instantly.

### 6.5 Source visibility rules

- Curated (global) sources are visible to everyone on Home, whether or not you're logged in.
- Custom (user-submitted) sources are **never** shown on the public Home page — they only ever influence the personal feed/digest of people subscribed to them.
- There's currently no "browse other members' custom sources to discover new ones" page — you'll only see subscriptions you already hold (your own submissions, or ones you joined by submitting an identical feed URL).

---

## 7. Complete Navigation Map

```
AI Compass
│
├── Home ( / )                          — Public. The full, filterable news stream. Trending, Featured, Latest.
├── Search ( /search/ )                 — Public. Natural-language / keyword search across all content.
├── Pricing ( /pricing/ )               — Public. Free vs. Pro comparison, upgrade entry point.
│
├── My Feed ( /feed/ )                  — Requires login. Your personalized, ranked feed.
│     └── "Tune my feed" → Preferences
│
├── News ( /news/ )                     — Requires login. Simpler Articles/Videos browsing tabs,
│   ├── Videos ( /news/videos/ )          reached via "News" breadcrumb on detail pages.
│   ├── Article detail ( /news/article/<id>/ )
│   ├── Video detail ( /news/video/<id>/ )     — Pro: Chapters section on videos ≥20 min
│   └── Story Cluster ( /news/story/<type>/<id>/ ) — "Same story, every source" view
│
├── Sources ( /onboarding/sources/ )    — Requires login. Add/manage custom & curated sources.
│
├── People ( /news/people/ )            — Requires login. Browse and follow tracked people.
│   └── Entity / Person profile ( /entity/<id>/ ) — own content, mentions, related entities, mention timeline
│
├── Insights ( /insights/ )             — Requires login + Pro. Weekly cited trend briefing.
│
├── Library ( /behavior/library/ )      — Requires login. Saved items + Read history.
│
└── Account menu (avatar, top-right)
    ├── Profile ( /accounts/profile/ )        — Identity + ranking/digest preferences
    ├── Billing ( /accounts/billing/ )        — Plan status, usage, upgrade/manage subscription
    ├── Preferences ( /onboarding/preferences/ ) — Interest tags
    ├── Onboarding ( /onboarding/ )           — Only shown until you've completed it once
    ├── Ops Dashboard ( /ops/ )               — Staff only. Source health monitoring.
    └── Log out

Auth pages (unauthenticated users only)
├── Log in ( /accounts/login/ )
├── Sign up ( /accounts/register/ )
├── Forgot password ( /accounts/password_reset/ → done → emailed link → confirm → complete )
└── Email verification ( link emailed at signup; "Resend verification email" available anytime )
```

### Page-by-page access & actions summary

| Page | Who can access | Key actions available |
|---|---|---|
| Home | Everyone | Browse, search, filter by category/source/topic/date, save, hide (logged-in only) |
| Search | Everyone | Natural-language or keyword search, save, hide (logged-in only) |
| Pricing | Everyone | Compare plans, upgrade to Pro (login required to actually upgrade) |
| My Feed | Logged-in | View ranked feed, jump to Preferences, save, hide |
| News / Videos lists | Logged-in | Browse a simpler chronological list, filter by source/keyword |
| Article / Video detail | Logged-in | Read/watch, save, hide, follow topics & mentioned entities, see related coverage |
| Story Cluster | Logged-in | See every source covering the same story |
| Sources | Logged-in | Submit a custom source, subscribe/unsubscribe, include/exclude curated sources |
| People | Logged-in | Search people, follow/unfollow |
| Entity/Person profile | Logged-in | View mention history, own content, related entities, follow/unfollow |
| Insights | Logged-in (Pro for content) | Read the weekly cited trend briefing |
| Library | Logged-in | Review saved items, review read history, unsave |
| Profile | Logged-in | Edit identity, digest cadence, ranking preferences |
| Billing | Logged-in | View plan/usage, upgrade, manage subscription |
| Preferences | Logged-in | Choose interest tags |
| Onboarding wizard | Logged-in, first time only | Set persona, interests, and initial source exclusions |
| Ops Dashboard | Staff only | Monitor source health (read-only) |

---

## 8. End-to-End User Scenarios

### Scenario 1 — A visitor wants to try the product before signing up
1. Visit the Home page — no account needed.
2. Use the **Search** box or the category/source/topic filters to explore what's being tracked.
3. Click **Read more** on an interesting item — this opens the source's own site directly (no login gate on the external link itself), though the AI Compass detail page (summary, "why it matters," related coverage) requires logging in first.
4. Decide to sign up: click **Sign up**, fill in email/password, and land straight in the onboarding wizard.

### Scenario 2 — A free user wants to follow AI news from a specific website
1. Log in and open **Sources** from the top nav.
2. In **"Add your own source,"** paste the site's RSS/Atom feed URL, give it a name, and pick a category.
3. Submit — within a few seconds, a message confirms whether it was accepted (and you're auto-subscribed) or rejected as off-topic.
4. From then on, that source's content appears in **My Feed** and in your digest email, without ever showing up on the public Home page.
5. If they later want to stop, they open **Sources** again and click the **×** on that subscription chip.

### Scenario 3 — A new user gets from signup to a personalized feed
1. Sign up (§3.1) → land in the onboarding wizard.
2. Pick a persona (e.g., "Engineer / Developer"), select a handful of interests (e.g., LLMs, AI Agents, Developer Tools), skip the sources step (defaults to everything included), click **Finish**.
3. Land on **My Feed**, which initially shows the newest content (filtered by any exclusions) with a note that real ranking appears after the first digest run.
4. Over the next day, the ranking engine processes their interests/persona and My Feed starts showing ranked items with **"Recommended for you"** reasoning.
5. They fine-tune further via **Profile** (technical level, article/video mix) and **Preferences** (add/remove interest tags) as their taste becomes clearer.

### Scenario 4 — A free user hits a limit and upgrades
1. While browsing People and Entity profiles, a user follows their 20th topic/person and the 21st attempt shows: *"Free accounts can follow up to 20 — upgrade to Pro for unlimited."*
2. They open **Pricing**, compare Free vs. Pro, and click **Upgrade to Pro**.
3. If their email isn't verified yet, checkout stops them with a reminder to verify first — they click **Resend verification email**, verify via the emailed link, and retry.
4. They complete payment on Stripe's hosted checkout page, land back on AI Compass with a "processing" message, and within seconds their **Billing** page shows the Pro badge and unlimited usage.
5. They immediately follow the topic/person that had been blocked.

### Scenario 5 — A Pro user wants to customize their feed around specific topics
1. Open **Preferences** and select every relevant interest tag (e.g., AI Safety & Alignment, RAG & Vector Databases, MLOps & Infrastructure) — save.
2. Open **Profile** and set **Technical level** to Advanced, **Research vs. industry lean** to Research-leaning, and a **Reading-time budget** that matches how much time they actually have per day.
3. Go to **Sources** and exclude any curated categories that are just noise for them (e.g., Government, Funding), while adding one or two custom niche blogs via "Add your own source" — unlimited on Pro.
4. Follow the specific people and topics they care most about, again unlimited on Pro.
5. Over subsequent digest runs, **My Feed** reflects all of these signals together, and the weekly **Insights** briefing (Pro-only) starts arriving by email as well.

### Scenario 6 — A user discovers something trending and follows it
1. On Home, the **Trending** row shows a topic pill with a multiplier badge (e.g., "3.2x").
2. Clicking it (or a related article) leads to that topic's context — following the entity/person/topic chip on a detail page adds it to their tracked list.
3. From then on, that topic/person's page (`/entity/<id>/`) shows a 90-day mention sparkline and any related entities, and matching content is boosted in **My Feed**.

### Scenario 7 — A user saves articles to read later
1. While scanning Home or My Feed, they click the bookmark icon on a few interesting cards — each saves instantly, no page reload.
2. Later, they open **Library** → **Saved** to see everything they've bookmarked, most recent first.
3. After reading one, they can leave it saved, or click the (now-filled) bookmark icon again to remove it.
4. Separately, everything they've actually opened (whether saved or not) appears automatically in **Library → Read history**.

### Scenario 8 — A free user watches a long video and hits the chapters limit
1. They open a 45-minute YouTube video's detail page.
2. Below the summary, instead of a chapter breakdown, they see a locked card: *"🔒 Chaptered summary is a Pro feature — This is a long-form video — upgrade to Pro to get a chapter-by-chapter breakdown with clickable timestamps."*
3. Everything else on the page (summary, why it matters, related coverage, follow chips) works normally — only the chapters section is gated.
4. If they upgrade to Pro, revisiting the same video now shows the full chapter list with clickable timestamps.

### Scenario 9 — A user resets a forgotten password
1. On the login page, click **Forgot password?**.
2. Enter their account email, click **Send reset link**, and see the "check your email" confirmation.
3. Open the emailed reset link, set a new password on the confirmation page, and click **Set password**.
4. Land on a "Password updated" confirmation page and click **Log in** to sign back in with the new password.

---

## 9. Quick Reference: Free vs. Pro

| Capability | Free | Pro |
|---|---|---|
| Browse Home, Search, Pricing | ✅ | ✅ |
| Personalized My Feed, digest emails | ✅ | ✅ |
| Save, hide, read history (Library) | ✅ Unlimited | ✅ Unlimited |
| Interests, persona, ranking preferences | ✅ Unlimited | ✅ Unlimited |
| Semantic (meaning-based) search | ✅ | ✅ |
| Follow topics / people / entities | Up to **20** | **Unlimited** |
| Custom (self-submitted) sources | Up to **3** | **Unlimited** |
| Chaptered summaries on videos ≥20 min | ❌ (upsell shown) | ✅ |
| Speech-to-text for caption-less videos | Processed for everyone; only the resulting chapters are Pro-gated | ✅ |
| Weekly grounded trend briefing (Insights page + email) | ❌ (upsell shown) | ✅ |

---

*This guide reflects the product as of the most recent walkthrough of the live application. Feature names, limits, and messages were verified directly against the running site and its templates rather than assumed.*
