import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import SourcesPage from '@/components/pages/SourcesPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="sources" />
      <SourcesPage />
    </AppShell>
  );
}
