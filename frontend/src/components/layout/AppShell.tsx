'use client';

import Sidebar from './Sidebar';
import TopBar from './TopBar';
import MobileNav from './MobileNav';
import AIAssistant from '@/components/assistant';
import { useAppStore } from '@/lib/store';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { currentPage } = useAppStore();
  const isAuthPage = ['login', 'signup', 'forgot-password', 'password-reset-done', 'onboarding'].includes(currentPage);

  if (isAuthPage) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background px-4 py-8">
        <div className="w-full max-w-md animate-fade-in">
          {children}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 pb-20 lg:pb-6">
          <div className="animate-fade-in">
            {children}
          </div>
        </main>
      </div>
      <MobileNav />
      <AIAssistant />
    </div>
  );
}