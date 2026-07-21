'use client';

import { Search, Bell, Menu, ArrowLeft, Sun, Moon, Monitor } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTheme } from 'next-themes';
import { useAppStore } from '@/lib/store';

const PAGE_TITLES: Record<string, string> = {
  search: 'Search',
  feed: 'My Feed',
  pricing: 'Pricing',
  sources: 'Sources',
  people: 'People',
  library: 'Library',
  insights: 'Insights',
  profile: 'Profile',
  billing: 'Billing',
  preferences: 'Preferences',
  onboarding: 'Get Started',
  login: 'Log In',
  signup: 'Sign Up',
  'forgot-password': 'Reset Password',
  'password-reset-done': 'Check Your Email',
};

export default function TopBar() {
  const { currentPage, navigate, goBack, setSidebarOpen, isLoggedIn, user, logout, previousPage } = useAppStore();
  const { setTheme, theme } = useTheme();

  const isDetailPage = currentPage === 'article-detail' || currentPage === 'video-detail' || currentPage === 'entity-profile';
  const isHomePage = currentPage === 'home';
  const isAuthPage = ['login', 'signup', 'forgot-password', 'password-reset-done', 'onboarding'].includes(currentPage);

  if (isAuthPage || isDetailPage) return null;

  const title = PAGE_TITLES[currentPage] || '';

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md md:px-6">
      {/* Mobile menu */}
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={() => setSidebarOpen(true)}
      >
        <Menu className="h-5 w-5" />
      </Button>

      {isHomePage ? (
        <div className="mx-auto w-full max-w-xl">
          <button
            onClick={() => navigate('search')}
            className="flex w-full items-center gap-2.5 rounded-lg border border-border bg-muted/50 px-3.5 py-2 text-sm text-ink-muted transition-colors duration-150 hover:bg-muted"
          >
            <Search className="h-4 w-4" />
            <span>Search AI news...</span>
            <kbd className="ml-auto hidden rounded border border-border bg-surface px-1.5 py-0.5 text-[11px] font-medium text-ink-muted sm:inline-flex">
              ⌘K
            </kbd>
          </button>
        </div>
      ) : (
        <>
          {previousPage && (
            <Button variant="ghost" size="icon" className="shrink-0" onClick={goBack}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
          )}
          <h1 className="text-base font-semibold text-ink">{title}</h1>
        </>
      )}

      <div className="ml-auto flex items-center gap-1.5">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="text-ink-muted">
              {theme === 'dark' ? <Moon className="h-4.5 w-4.5" /> : theme === 'light' ? <Sun className="h-4.5 w-4.5" /> : <Monitor className="h-4.5 w-4.5" />}
              <span className="sr-only">Toggle theme</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-36">
            <DropdownMenuItem onClick={() => setTheme('light')} className={theme === 'light' ? 'bg-accent' : ''}>
              <Sun className="mr-2 h-4 w-4" /> Light
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme('dark')} className={theme === 'dark' ? 'bg-accent' : ''}>
              <Moon className="mr-2 h-4 w-4" /> Dark
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme('system')} className={theme === 'system' ? 'bg-accent' : ''}>
              <Monitor className="mr-2 h-4 w-4" /> System
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {isLoggedIn && user ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center">
                <Avatar className="h-7 w-7">
                  <AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">
                    {user.name.split(' ').map(n => n[0]).join('')}
                  </AvatarFallback>
                </Avatar>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem onClick={() => navigate('profile')}>
                Profile
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('billing')}>
                Billing
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('preferences')}>
                Preferences
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <Button size="sm" variant="outline" onClick={() => navigate('login')} className="text-xs">
            Log in
          </Button>
        )}
      </div>
    </header>
  );
}