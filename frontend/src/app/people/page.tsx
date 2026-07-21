import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import PeoplePage from '@/components/pages/PeoplePage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="people" />
      <PeoplePage />
    </AppShell>
  );
}
