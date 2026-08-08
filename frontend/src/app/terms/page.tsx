import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import TermsPage from '@/components/pages/TermsPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="terms" />
      <TermsPage />
    </AppShell>
  );
}
