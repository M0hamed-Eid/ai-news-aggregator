'use client';

// M16 — Privacy Policy. Every data-collection claim here is grounded in
// the production-readiness audit's actual data inventory
// (docs/PRODUCTION_READINESS_AUDIT.md Section 11 — built from real model
// fields, not assumption). Confirmed via repo-wide grep specifically: NO
// IP address capture, NO User-Agent/device fingerprinting, NO third-party
// analytics or tracking scripts exist anywhere in this codebase — this
// page says so because it's true, not as a generic privacy-page claim.
// Version string MUST match web/apps/accounts/legal.py's
// CURRENT_PRIVACY_VERSION exactly.
const PRIVACY_VERSION = '2026-08-08';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-ink-muted">{children}</div>
    </section>
  );
}

const DATA_TABLE: { data: string; why: string; retention: string }[] = [
  { data: 'Email address', why: 'Account login and identity', retention: 'Until account deletion' },
  { data: 'First/last name', why: 'Personalization (optional, may be left blank)', retention: 'Until account deletion' },
  { data: 'Password', why: 'Login — stored as a salted hash, never in plain text', retention: 'Until account deletion' },
  { data: 'Plan / billing status', why: 'Determines which features you can access', retention: 'Until account deletion' },
  { data: 'Persona, bio, interests, excluded topics/sources', why: 'Feed personalization (all optional, set during onboarding or Preferences)', retention: 'Until account deletion' },
  { data: 'Saved / hidden / read items', why: 'Powers the Library feature', retention: 'Until account deletion' },
  { data: 'Behavioral events (impressions, clicks, dwell time, scroll depth, searches)', why: 'Improves your personalized ranking over time', retention: '90 days, then automatically deleted' },
  { data: 'Digest email settings and send history', why: 'Controls and records your weekly/periodic email digest', retention: 'Until account deletion' },
];

export default function PrivacyPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-10">
      <h1 className="mb-1 text-2xl font-bold text-ink">Privacy Policy</h1>
      <p className="mb-8 text-sm text-ink-muted">Effective date / version: {PRIVACY_VERSION}</p>

      <div className="space-y-8">
        <Section title="What this policy covers">
          <p>
            This page explains exactly what personal data AI Compass collects, why, where it&apos;s stored, and
            what rights you have over it. Every item below reflects what the application actually does, verified
            directly against its code — not a generic template.
          </p>
        </Section>

        <Section title="Data we collect">
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-card text-ink">
                <tr>
                  <th className="p-2 font-medium">Data</th>
                  <th className="p-2 font-medium">Why we collect it</th>
                  <th className="p-2 font-medium">Retention</th>
                </tr>
              </thead>
              <tbody>
                {DATA_TABLE.map((row) => (
                  <tr key={row.data} className="border-t border-border">
                    <td className="p-2 align-top">{row.data}</td>
                    <td className="p-2 align-top">{row.why}</td>
                    <td className="p-2 align-top">{row.retention}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="What we do NOT collect">
          <p>Confirmed directly in the codebase, not just stated as policy:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>We do not capture your IP address anywhere in the application.</li>
            <li>We do not capture your browser User-Agent or any device fingerprint.</li>
            <li>We do not use any third-party analytics, advertising, or tracking scripts (no Google Analytics, no Meta Pixel, no similar tool of any kind).</li>
            <li>We do not set any cookie beyond the two required to run the site itself: a session cookie (keeps you logged in) and a CSRF-protection cookie (blocks cross-site request forgery). Neither is used for tracking or advertising.</li>
          </ul>
        </Section>

        <Section title="How your data is used">
          <ul className="list-disc space-y-1 pl-5">
            <li>Your interests, follows, and behavioral events feed a ranking system that personalizes your feed and digest — this processing happens entirely within AI Compass&apos;s own systems.</li>
            <li>Article/video text is sent to our AI provider (Groq) to generate summaries and power the chat assistant. Your personal account data (email, password, saved items, etc.) is never included in those calls — only the content being summarized and, for the chat assistant, your question text.</li>
            <li>Your email address is used to send you the digest emails you&apos;ve configured, and account-related emails (verification, password reset).</li>
          </ul>
        </Section>

        <Section title="Where data is stored, and who processes it">
          <p>All data is stored in a PostgreSQL database. The following third-party services process data on our behalf:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li><strong className="text-ink">Neon</strong> — hosts the production database (all data in the table above).</li>
            <li><strong className="text-ink">Render</strong> — hosts the backend application server that processes your requests.</li>
            <li><strong className="text-ink">Vercel</strong> — hosts the frontend web application you interact with in your browser.</li>
            <li><strong className="text-ink">Groq</strong> — processes article/video text (for summaries) and your chat questions (for the assistant feature) to generate AI output. Does not receive your account credentials.</li>
            <li><strong className="text-ink">Email provider (Gmail SMTP)</strong> — used to deliver digest and account-related emails; receives your email address and the email content.</li>
            <li><strong className="text-ink">GitHub Actions</strong> — runs the scheduled content pipeline (scraping/enrichment/ranking); does not process individual user account data, only the shared content catalog and ranking computation.</li>
            <li><strong className="text-ink">Stripe</strong> (Pro plan only) — processes payment information directly; AI Compass never receives or stores your card details.</li>
          </ul>
        </Section>

        <Section title="Data retention">
          <p>
            Behavioral events (impressions, clicks, dwell, scroll, searches) are automatically deleted after 90
            days. Account data (profile, preferences, saved items, digest settings) is kept for as long as your
            account exists. Deleting your account removes or de-links this data — see &quot;Your rights&quot;
            below.
          </p>
        </Section>

        <Section title="Security">
          <p>
            Passwords are stored as salted hashes, never in plain text. All traffic to the site is served over
            HTTPS. Access to the production database is restricted to the application itself and its
            administrators.
          </p>
        </Section>

        <Section title="Your rights">
          <ul className="list-disc space-y-1 pl-5">
            <li><strong className="text-ink">Access:</strong> view your account information from your Profile page at any time.</li>
            <li><strong className="text-ink">Correction:</strong> update your name, interests, preferences, and digest settings yourself, at any time.</li>
            <li>
              <strong className="text-ink">Deletion:</strong> delete your account from Account Settings. This
              permanently removes your profile, preferences, saved items, follows, and behavioral history.
              Shared catalog content (articles, videos, and other content that isn&apos;t specific to you) is
              never deleted just because one account is removed — it belongs to the shared platform, not to any
              individual user.
            </li>
          </ul>
        </Section>

        <Section title="Legal basis / regional compliance">
          <p className="rounded-md border border-border bg-card p-3 text-xs italic">
            Flagged for review, not asserted: this policy describes what data is collected and how truthfully,
            but does not claim compliance with any specific data-protection law (including Egypt&apos;s Personal
            Data Protection Law or any other jurisdiction&apos;s requirements). If legal compliance certification
            is required, have this policy and the underlying data practices reviewed by qualified legal counsel.
          </p>
        </Section>

        <Section title="Changes to this policy">
          <p>
            If this policy changes materially, we&apos;ll ask you to re-acknowledge the current version the next
            time you log in.
          </p>
        </Section>

        <Section title="Contact">
          <p>
            Questions about this policy, or a request to access/correct/delete your data, can be sent to the
            contact address listed on the service&apos;s support page.{' '}
            <span className="italic">
              (Flagged for review: a real support/contact email should be filled in here before this page is
              published live.)
            </span>
          </p>
        </Section>
      </div>
    </div>
  );
}
