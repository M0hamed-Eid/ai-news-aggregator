import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import SearchPage from '@/components/pages/SearchPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="search" />
      <SearchPage />
    </AppShell>
  );
}
