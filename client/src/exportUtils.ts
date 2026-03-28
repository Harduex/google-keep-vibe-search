import { Note } from '@/types';

export function formatNotesAsTxt(notes: Note[]): string {
  return notes
    .map((note) => [note.title, note.content].filter(Boolean).join('\n\n'))
    .join('\n\n---\n\n');
}

export function downloadAsTxt(content: string, filename: string): void {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function exportNotes(notes: Note[], filename: string): void {
  downloadAsTxt(formatNotesAsTxt(notes), filename);
}

export function todayDateStr(): string {
  return new Date().toISOString().slice(0, 10);
}
