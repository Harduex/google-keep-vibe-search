export const THEME_TYPES = {
  LIGHT: 'light',
  DARK: 'dark',
} as const;

export type ThemeType = keyof typeof THEME_TYPES;

export const NOTE_COLORS = {
  RED: 'RED',
  ORANGE: 'ORANGE',
  YELLOW: 'YELLOW',
  GREEN: 'GREEN',
  TEAL: 'TEAL',
  BLUE: 'BLUE',
  PURPLE: 'PURPLE',
  BROWN: 'BROWN',
  GRAY: 'GRAY',
  DEFAULT: 'DEFAULT',
} as const;

export type NoteColor = keyof typeof NOTE_COLORS;
