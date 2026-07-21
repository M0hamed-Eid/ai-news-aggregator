import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import LibraryPage from '@/components/pages/LibraryPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="library" />
      <LibraryPage />
    </AppShell>
  );
}
