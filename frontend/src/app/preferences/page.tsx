import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import PreferencesPage from '@/components/pages/PreferencesPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="preferences" />
      <PreferencesPage />
    </AppShell>
  );
}
