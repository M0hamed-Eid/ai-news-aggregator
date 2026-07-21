import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import OnboardingPage from '@/components/pages/OnboardingPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="onboarding" />
      <OnboardingPage />
    </AppShell>
  );
}
