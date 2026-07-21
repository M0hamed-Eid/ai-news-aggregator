import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import PricingPage from '@/components/pages/PricingPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="pricing" />
      <PricingPage />
    </AppShell>
  );
}
