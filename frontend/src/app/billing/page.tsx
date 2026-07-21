import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import BillingPage from '@/components/pages/BillingPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="billing" />
      <BillingPage />
    </AppShell>
  );
}
