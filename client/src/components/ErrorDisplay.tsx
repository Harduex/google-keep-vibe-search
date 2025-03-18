import { memo } from 'react';

interface ErrorDisplayProps {
  error: string | null;
  onDismiss: () => void;
}

export const ErrorDisplay = memo(({ error, onDismiss }: ErrorDisplayProps) => {
  if (!error) {
    return null;
  }

  return (
    <div className="error-container">
      <div className="error-message">
        <span className="material-icons">error</span>
        <p>{error}</p>
        <button className="error-dismiss" onClick={onDismiss}>
          <span className="material-icons">close</span>
        </button>
      </div>
    </div>
  );
});

ErrorDisplay.displayName = 'ErrorDisplay';
