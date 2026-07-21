'use client';

import { useParams } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import ArticleDetailPage from '@/components/pages/ArticleDetailPage';

export default function Page() {
  const params = useParams<{ id: string }>();
  return (
    <AppShell>
      <PageSync page="article-detail" params={{ id: params.id }} />
      <ArticleDetailPage />
    </AppShell>
  );
}
