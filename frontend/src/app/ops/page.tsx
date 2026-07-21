import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import OpsPage from '@/components/pages/OpsPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="ops" />
      <OpsPage />
    </AppShell>
  );
}
