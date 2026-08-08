import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import PrivacyPage from '@/components/pages/PrivacyPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="privacy" />
      <PrivacyPage />
    </AppShell>
  );
}
