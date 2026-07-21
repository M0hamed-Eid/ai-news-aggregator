import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import InsightsPage from '@/components/pages/InsightsPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="insights" />
      <InsightsPage />
    </AppShell>
  );
}
