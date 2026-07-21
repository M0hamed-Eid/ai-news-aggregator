import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import ProfilePage from '@/components/pages/ProfilePage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="profile" />
      <ProfilePage />
    </AppShell>
  );
}
