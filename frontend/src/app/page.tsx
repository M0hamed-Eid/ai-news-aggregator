import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import HomePage from '@/components/pages/HomePage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="home" />
      <HomePage />
    </AppShell>
  );
}
