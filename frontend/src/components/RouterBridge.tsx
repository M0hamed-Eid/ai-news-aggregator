'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { setRouterInstance } from '@/lib/router-bridge';

/** Mounted once in the root layout — makes the real Next.js router reachable
 * from the Zustand store's plain (non-hook) navigate()/goBack() actions. */
export default function RouterBridge() {
  const router = useRouter();
  useEffect(() => {
    setRouterInstance(router);
  }, [router]);
  return null;
}
