import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import PasswordResetDonePage from '@/components/pages/PasswordResetDonePage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="password-reset-done" />
      <PasswordResetDonePage />
    </AppShell>
  );
}
