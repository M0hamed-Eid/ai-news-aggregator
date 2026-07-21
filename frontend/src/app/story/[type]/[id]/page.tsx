'use client';

import { useParams } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import StoryClusterPage from '@/components/pages/StoryClusterPage';

export default function Page() {
  const params = useParams<{ type: string; id: string }>();
  return (
    <AppShell>
      <PageSync page="story-cluster" params={{ type: params.type, id: params.id }} />
      <StoryClusterPage />
    </AppShell>
  );
}
