'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from 'react';

type Theme = 'light' | 'dark' | 'system';
type ResolvedTheme = 'light' | 'dark';

type ThemeContextValue = {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  systemTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
  themes: Theme[];
};

const STORAGE_KEY = 'theme';
const THEME_VALUES: Theme[] = ['light', 'dark', 'system'];
const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function subscribe(callback: () => void) {
  window.addEventListener('storage', callback);
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', callback);

  return () => {
    window.removeEventListener('storage', callback);
    window.matchMedia('(prefers-color-scheme: dark)').removeEventListener('change', callback);
  };
}

function getStoredTheme(): Theme {
  const theme = localStorage.getItem(STORAGE_KEY);
  return THEME_VALUES.includes(theme as Theme) ? (theme as Theme) : 'system';
}

function getSystemTheme(): ResolvedTheme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getSnapshot() {
  const theme = getStoredTheme();
  const systemTheme = getSystemTheme();

  return JSON.stringify({ theme, systemTheme });
}

function getServerSnapshot() {
  return JSON.stringify({ theme: 'system' satisfies Theme, systemTheme: 'light' satisfies ResolvedTheme });
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const { theme, systemTheme } = JSON.parse(snapshot) as { theme: Theme; systemTheme: ResolvedTheme };
  const resolvedTheme = theme === 'system' ? systemTheme : theme;

  const setTheme = useCallback((nextTheme: Theme) => {
    localStorage.setItem(STORAGE_KEY, nextTheme);
    window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY, newValue: nextTheme }));
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(resolvedTheme);
    root.style.colorScheme = resolvedTheme;
  }, [resolvedTheme]);

  const value = useMemo(
    () => ({ theme, resolvedTheme, systemTheme, setTheme, themes: THEME_VALUES }),
    [theme, resolvedTheme, systemTheme, setTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }

  return context;
}

export function useHasMounted() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );
}
