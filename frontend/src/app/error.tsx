'use client';

// Production error boundary (M16 — found missing entirely during the
// production-readiness audit: with no error.tsx, an unhandled render error
// anywhere in the app showed Next.js's bare default error screen, with no
// recovery path and no branding). Catches any error thrown while rendering
// this route segment or below; does NOT catch errors in the root layout
// itself (RootLayout, ThemeProvider, Providers) — see global-error.tsx for
// that narrower case.

import { useEffect } from 'react';
import { Button } from '@/components/ui/button';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Client-side only, real user impact — worth a console trace even
    // without a paid error-tracking service. Never includes anything from
    // request/response bodies (this is a render-time error object only).
    console.error('Unhandled application error:', error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-semibold text-ink">Something went wrong</h1>
      <p className="max-w-md text-sm text-ink-muted">
        An unexpected error occurred. This has been logged — try again, or head back to the home page.
      </p>
      <div className="flex gap-3">
        <Button onClick={() => reset()}>Try again</Button>
        <Button variant="outline" onClick={() => { window.location.href = '/'; }}>
          Go home
        </Button>
      </div>
    </div>
  );
}
