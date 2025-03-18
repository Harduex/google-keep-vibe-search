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
 * Format statistics text
 */
export const formatStatsText = (
  totalNotes?: number,
  archivedNotes?: number,
  pinnedNotes?: number
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
