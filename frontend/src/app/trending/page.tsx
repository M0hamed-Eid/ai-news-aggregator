import AppShell from '@/components/layout/AppShell';
import PageSync from '@/components/PageSync';
import TrendingStoriesPage from '@/components/pages/TrendingStoriesPage';

export default function Page() {
  return (
    <AppShell>
      <PageSync page="trending-stories" />
      <TrendingStoriesPage />
    </AppShell>
  );
}
