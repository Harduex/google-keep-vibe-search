export const UI_ELEMENTS = {
  NOTE_MAX_HEIGHT: 150,
  ANIMATION_DURATION: 300,
  DEFAULT_SCROLL_BEHAVIOR: 'smooth' as const,
  SEARCH_OFFSET: 20,
};

export const API_ROUTES = {
  STATS: '/api/stats',
  SEARCH: '/api/search',
  IMAGE: '/api/image',
  EMBEDDINGS: '/api/embeddings',
  CLUSTERS: '/api/clusters',
  ALL_NOTES: '/api/all-notes',
};

export const VIEW_MODES = {
  LIST: 'list',
  VISUALIZATION: '3d',
} as const;

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
