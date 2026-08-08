'use client';

// Catches an error in the ROOT LAYOUT itself (ThemeProvider/Providers/
// RouterBridge/SessionHydrator init failing), which error.tsx cannot —
// Next.js requires this file to render its own full <html><body> since it
// replaces the root layout entirely when triggered. Deliberately minimal:
// no Tailwind/theme dependency, since the very providers that would supply
// theming are what may have failed to render.

import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Unhandled root-layout error:', error);
  }, [error]);

  return (
    <html lang="en">
      <body style={{ background: '#0a0a0f', color: '#e5e5e5', fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1rem', padding: '1.5rem', textAlign: 'center' }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 600 }}>Something went wrong</h1>
          <p style={{ maxWidth: '28rem', fontSize: '0.875rem', color: '#a1a1aa' }}>
            The application failed to load. Try again, or reload the page.
          </p>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              onClick={() => reset()}
              style={{ padding: '0.5rem 1rem', borderRadius: '0.375rem', background: '#6366f1', color: 'white', border: 'none', cursor: 'pointer' }}
            >
              Try again
            </button>
            <button
              onClick={() => { window.location.href = '/'; }}
              style={{ padding: '0.5rem 1rem', borderRadius: '0.375rem', background: 'transparent', color: '#e5e5e5', border: '1px solid #3f3f46', cursor: 'pointer' }}
            >
              Go home
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
