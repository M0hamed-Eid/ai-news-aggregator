import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import FeedPage from '@/components/pages/FeedPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="feed" />
      <FeedPage />
    </AppShell>
  );
}
