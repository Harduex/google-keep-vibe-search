/**
 * Sanitize HTML content to prevent XSS
 */
export const sanitizeHTML = (text: string): string => {
  if (!text) {
    return '';
  }
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

/**
 * Highlight search matches in text
 */
export const highlightMatches = (text: string, query: string): string => {
  if (!text || !query) {
    return sanitizeHTML(text);
  }

  const sanitizedText = sanitizeHTML(text);
  const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escapedQuery})`, 'gi');

  return sanitizedText.replace(regex, '<mark>$1</mark>');
};

/**
 * Parse comma-separated keywords for refinement search
 */
export const parseKeywords = (keywordsString: string): string[] => {
  if (!keywordsString) {
    return [];
  }

  return keywordsString
    .split(',')
    .map((keyword) => keyword.trim().toLowerCase())
    .filter((keyword) => keyword.length > 0);
};

/**
 * Check if text contains all the specified keywords
 */
export const containsKeywords = (text: string, keywords: string[]): boolean => {
  if (!text || !keywords || keywords.length === 0) {
    return true;
  }

  const lowerText = text.toLowerCase();
  return keywords.every((keyword) => lowerText.includes(keyword));
};

/**
 * Filter notes based on refinement keywords
 */
export const filterByKeywords = <T extends { title?: string; content: string }>(
  items: T[],
  keywordsString: string,
): T[] => {
  const keywords = parseKeywords(keywordsString);

  if (keywords.length === 0) {
    return items;
  }

  return items.filter((item) => {
    const titleContent = [item.title || '', item.content].join(' ');
    return containsKeywords(titleContent, keywords);
  });
};

/**
 * Format statistics text
 */
export const formatStatsText = (
  totalNotes?: number,
  archivedNotes?: number,
  pinnedNotes?: number,
): string => {
  if (totalNotes === undefined) {
    return 'Loading notes...';
  }

  const details = [];

  if (archivedNotes && archivedNotes > 0) {
    details.push(`${archivedNotes} archived`);
  }

  if (pinnedNotes && pinnedNotes > 0) {
    details.push(`${pinnedNotes} pinned`);
  }

  return details.length > 0
    ? `${totalNotes} notes loaded (${details.join(', ')})`
    : `${totalNotes} notes loaded`;
};

/**
 * Safely scroll to element
 */
export const scrollToElement = (selector: string, offset = 0): void => {
  const element = document.querySelector(selector);
  if (element) {
    window.scrollTo({
      top: element.getBoundingClientRect().top + window.scrollY - offset,
      behavior: 'smooth',
    });
  }
};

/**
 * Calculate score percentage
 */
export const calculateScorePercentage = (score: number): number => {
  return Math.round(score * 100);
};

/**
 * Create URL for image API
 */
export const getImageUrl = (filePath: string): string => {
  return `/api/image/${encodeURIComponent(filePath)}`;
};
