'use client';

import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// One QueryClient per browser session (useState lazy-init, not module-level
// — module-level would leak cached data across users on the server in a
// framework that does SSR, and this app renders client components for every
// data-fetching page anyway). Mounted once in layout.tsx so every page's
// useQuery calls (Home/Feed/Search, see .claude/plans/effervescent-petting-
// nebula.md Phase 1) share one cache.
export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
