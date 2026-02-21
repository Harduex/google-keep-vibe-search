export const UI_ELEMENTS = {
  NOTE_MAX_HEIGHT: 150,
  ANIMATION_DURATION: 300,
  DEFAULT_SCROLL_BEHAVIOR: 'smooth' as const,
  SEARCH_OFFSET: 20,
};

export const API_ROUTES = {
  STATS: '/api/stats',
  SEARCH: '/api/search',
  SEARCH_BY_IMAGE: '/api/search/image',
  IMAGE: '/api/image',
  EMBEDDINGS: '/api/embeddings',
  CLUSTERS: '/api/clusters',
  ALL_NOTES: '/api/all-notes',
  CHAT: '/api/chat',
  CHAT_MODEL: '/api/chat/model',
  CHAT_SESSIONS: '/api/chat/sessions',
  TAGS: '/api/tags',
  TAG_NOTES: '/api/notes/tag',
  EXCLUDED_TAGS: '/api/tags/excluded',
  REMOVE_TAG: '/api/notes',
  REMOVE_TAG_FROM_ALL: '/api/tags/remove',
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
