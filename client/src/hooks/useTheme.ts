import { useEffect, useState, useCallback } from 'react';

// Move theme constants here since they're only used in this hook
const THEME_TYPES = {
  LIGHT: 'light',
  DARK: 'dark',
} as const;

type ThemeType = keyof typeof THEME_TYPES;

interface UseThemeResult {
  theme: ThemeType;
  toggleTheme: () => void;
}

export const useTheme = (): UseThemeResult => {
  const [theme, setTheme] = useState<ThemeType>(() => {
    const savedTheme = localStorage.getItem('theme');
    // Check if the saved theme matches any of our keys directly
    if (savedTheme === 'LIGHT' || savedTheme === 'DARK') {
      return savedTheme as ThemeType;
    }

    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    return prefersDark ? 'DARK' : 'LIGHT';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', THEME_TYPES[theme]);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prevTheme) => (prevTheme === 'DARK' ? 'LIGHT' : 'DARK'));
  }, []);

  return { theme, toggleTheme };
};
