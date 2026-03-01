import { memo } from 'react';

/**
 * Fullscreen overlay that matches the app's visual language.  It uses the
 * same font, colors and spacing as other components and optionally displays a
 * custom message beneath a themed spinner.  Appears above all other content.
 */
interface LoadingScreenProps {
  /**
   * Message text shown below the spinner; when not provided a generic index-
   * related sentence is used so the component can be consumed without having
   * to specify anything.
   */
  message?: string;
}

export const LoadingScreen = memo(({ message }: LoadingScreenProps) => (
  <div
    className="fixed inset-0 flex items-center justify-center loading-overlay z-50"
    data-testid="loading-screen"
    role="status"
    aria-busy="true"
    aria-label="Loading"
  >
    <div className="text-center p-8">
      <div className="inline-flex space-x-2 loader-dots" aria-hidden="true">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
      </div>

      <p className="mt-6 text-lg font-medium text-secondary-color">
        {message || 'Preparing your search experience…'}
      </p>
      <p className="mt-2 text-sm text-gray-500">Google Keep Vibe Search</p>
    </div>
  </div>
));
