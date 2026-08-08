'use client';

// M16 — Terms of Use. Content is grounded in this app's ACTUAL behavior as
// confirmed by the production-readiness audit (docs/PRODUCTION_READINESS_
// AUDIT.md) — no invented legal claims, no claimed compliance with any
// specific law. Anything genuinely uncertain is flagged inline as needing
// human/legal review rather than asserted. Version string below MUST match
// web/apps/accounts/legal.py's CURRENT_TERMS_VERSION exactly — the backend
// records acceptance against that constant, not this page's text.
const TERMS_VERSION = '2026-08-08';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-ink-muted">{children}</div>
    </section>
  );
}

export default function TermsPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-10">
      <h1 className="mb-1 text-2xl font-bold text-ink">Terms of Use</h1>
      <p className="mb-8 text-sm text-ink-muted">Effective date / version: {TERMS_VERSION}</p>

      <div className="space-y-8">
        <Section title="What AI Compass is">
          <p>
            AI Compass is a personal news-tracking tool that collects publicly available AI-related articles,
            videos, and research from a curated set of sources, generates AI-assisted summaries of that content,
            and ranks it for you based on your stated interests and reading activity.
          </p>
        </Section>

        <Section title="Acceptable use">
          <p>You agree to use AI Compass only for lawful purposes. In particular, you agree not to:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Attempt to gain unauthorized access to any account, system, or data other than your own.</li>
            <li>Scrape, bulk-extract, or resell the service&apos;s content or output.</li>
            <li>Interfere with or disrupt the service (e.g. attempting to overload it, bypassing rate limits).</li>
            <li>Use an automated process to create accounts.</li>
            <li>Misrepresent your identity or impersonate another person.</li>
          </ul>
        </Section>

        <Section title="Your account">
          <p>
            You are responsible for maintaining the confidentiality of your password and for all activity under
            your account. Tell us if you believe your account has been compromised. You must provide a valid email
            address to register.
          </p>
        </Section>

        <Section title="Third-party content and aggregation">
          <p>
            Articles, videos, and other content shown in AI Compass originate from third-party sources (news
            sites, research publishers, YouTube channels, and similar) and remain the property of their
            respective owners. AI Compass links back to the original source for every item — we do not claim
            ownership of aggregated third-party content, and we do not host full third-party articles or videos
            ourselves.
          </p>
        </Section>

        <Section title="AI-generated summaries and recommendations">
          <p>
            Article and video summaries, &quot;why it matters&quot; explanations, topic tags, and the weekly trend
            briefing are generated with the help of AI language models. Recommendations and your personalized
            feed ranking are produced algorithmically from your interests and activity on the service.
          </p>
          <p className="font-medium text-ink">
            AI-generated content may be incomplete, out of date, or simply wrong. It is provided to help you
            triage what to read, not as a substitute for the original source. Always check the linked original
            source before relying on anything AI Compass summarizes, especially for anything consequential.
          </p>
        </Section>

        <Section title="Service availability">
          <p>
            AI Compass is provided on a best-effort basis. We do not guarantee the service will be available at
            all times, free of errors, or that any particular feature (including scheduled digest emails or the
            weekly trend briefing) will run on a fixed schedule without interruption. Features may be changed,
            limited, or removed as the service evolves.
          </p>
        </Section>

        <Section title="Free and paid plans">
          <p>
            AI Compass offers a free plan with limited features and a paid Pro plan with additional features, as
            described on the Pricing page. Pricing, included features, and plan limits may change; we&apos;ll make
            a reasonable effort to communicate material changes to paying users in advance.
          </p>
        </Section>

        <Section title="Changes to the service or these terms">
          <p>
            We may update these Terms as the service changes. When a change is material, we&apos;ll ask you to
            re-accept the current version the next time you log in (you can always see the effective version
            date at the top of this page).
          </p>
        </Section>

        <Section title="Suspension and termination">
          <p>
            We may suspend or terminate an account that violates the acceptable-use section above. You can delete
            your own account at any time from your account settings — see the Privacy Policy for exactly what
            happens to your data when you do.
          </p>
        </Section>

        <Section title="Intellectual property">
          <p>
            The AI Compass name, interface, and our own original text (excluding aggregated third-party content
            and AI-generated summaries of that content) belong to AI Compass. Third-party content remains the
            property of its original publishers.
          </p>
        </Section>

        <Section title="Disclaimer and limitation of liability">
          <p>
            AI Compass is provided &quot;as is,&quot; without warranties of any kind, express or implied,
            including as to accuracy, completeness, or fitness for a particular purpose — this applies especially
            to AI-generated summaries and recommendations, which may contain errors. To the fullest extent
            permitted by law, AI Compass is not liable for any indirect, incidental, or consequential damages
            arising from your use of the service.
          </p>
          <p className="rounded-md border border-border bg-card p-3 text-xs italic">
            This section is a plain-language statement, not a substitute for legal advice, and has not been
            reviewed by a lawyer. If you need enforceable liability protection, have this section (and the
            document as a whole) reviewed by qualified legal counsel before relying on it.
          </p>
        </Section>

        <Section title="Governing law">
          <p className="rounded-md border border-border bg-card p-3 text-xs italic">
            Flagged for review, not asserted: which jurisdiction&apos;s law governs these Terms, and where any
            dispute would be resolved, has not been determined here and should be set by whoever operates this
            service after appropriate legal review — including whether Egyptian law, another jurisdiction, or
            both apply given where the operator and users are located.
          </p>
        </Section>

        <Section title="Contact">
          <p>
            Questions about these Terms can be sent to the contact address listed on the service&apos;s support
            page.{' '}
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
