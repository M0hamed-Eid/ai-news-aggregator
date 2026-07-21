import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import SignupPage from '@/components/pages/SignupPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="signup" />
      <SignupPage />
    </AppShell>
  );
}
