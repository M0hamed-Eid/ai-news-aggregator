'use client';

import { useLayoutEffect } from 'react';
import { useAppStore } from '@/lib/store';
import type { PageRoute } from '@/lib/types';

/**
 * Syncs the real URL (this route + its params) INTO the Zustand store on
 * mount/param-change — the reverse direction of store.navigate()'s
 * router.push(). Every page component (ArticleDetailPage etc.) keeps
 * reading currentPage/pageParams from the store exactly as Z.ai wrote it;
 * this is the only thing that changes when the URL changes.
 * useLayoutEffect (not useEffect) so the store is correct before paint,
 * avoiding a one-frame flash of the previous page's params.
 */
export default function PageSync({
  page,
  params = {},
}: {
  page: PageRoute;
  params?: Record<string, string>;
}) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    useAppStore.setState({ currentPage: page, pageParams: params });
  }, [page, JSON.stringify(params)]);
  return null;
}
