'use client';

import { useParams } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import VideoDetailPage from '@/components/pages/VideoDetailPage';

export default function Page() {
  const params = useParams<{ id: string }>();
  return (
    <AppShell>
      <PageSync page="video-detail" params={{ id: params.id }} />
      <VideoDetailPage />
    </AppShell>
  );
}
