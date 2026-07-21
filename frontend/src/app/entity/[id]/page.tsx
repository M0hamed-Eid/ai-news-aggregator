'use client';

import { useParams } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import EntityProfilePage from '@/components/pages/EntityProfilePage';

export default function Page() {
  const params = useParams<{ id: string }>();
  return (
    <AppShell>
      <PageSync page="entity-profile" params={{ id: params.id }} />
      <EntityProfilePage />
    </AppShell>
  );
}
