'use client';

import { useEffect } from 'react';
import { Home, Search, Rss, Bookmark, Users } from 'lucide-react';
import { useAppStore } from '@/lib/store';

const MOBILE_TABS = [
  { id: 'home' as const, label: 'Home', icon: Home },
  { id: 'search' as const, label: 'Search', icon: Search },
  { id: 'feed' as const, label: 'Feed', icon: Rss, requiresAuth: true },
  { id: 'library' as const, label: 'Saved', icon: Bookmark, requiresAuth: true },
  { id: 'people' as const, label: 'People', icon: Users, requiresAuth: true },
];

export default function MobileNav() {
  const { currentPage, navigate, isLoggedIn } = useAppStore();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-surface/95 backdrop-blur-md lg:hidden">
      <div className="flex h-14 items-center justify-around">
        {MOBILE_TABS.map((tab) => {
          const isActive = currentPage === tab.id;
          const isLocked = tab.requiresAuth && !isLoggedIn;

          return (
            <button
              key={tab.id}
              onClick={() => {
                if (isLocked) {
                  navigate('login');
                  return;
                }
                navigate(tab.id);
              }}
              className={`flex flex-col items-center gap-0.5 px-3 py-1.5 transition-colors duration-150 ${
                isActive ? 'text-primary' : 'text-ink-muted'
              }`}
            >
              <tab.icon className="h-5 w-5" />
              <span className="text-[10px] font-medium">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}