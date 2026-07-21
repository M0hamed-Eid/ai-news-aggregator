import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import ForgotPasswordPage from '@/components/pages/ForgotPasswordPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="forgot-password" />
      <ForgotPasswordPage />
    </AppShell>
  );
}
