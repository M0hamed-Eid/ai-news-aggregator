import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import LoginPage from '@/components/pages/LoginPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="login" />
      <LoginPage />
    </AppShell>
  );
}
