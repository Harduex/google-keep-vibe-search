import React, { useCallback, useState } from 'react';

interface AgentAction {
  type: string;
  description: string;
}

interface AgentInfoProps {
  agentInfo: {
    enabled: boolean;
    active: boolean;
    notes_added?: number;
    error?: string;
    actions?: AgentAction[];
  } | null;
}

export const AgentInfo: React.FC<AgentInfoProps> = ({ agentInfo }) => {
  const [showActions, setShowActions] = useState(false);

  const toggleActions = useCallback(() => {
    setShowActions(!showActions);
  }, [showActions]);

  if (!agentInfo || !agentInfo.active) {
    return null;
  }

  // Map action types to appropriate icons
  const getActionIcon = (type: string) => {
    switch (type) {
      case 'start':
        return 'play_arrow';
      case 'evaluate_context':
        return 'analytics';
      case 'decision':
        return 'lightbulb';
      case 'generate_queries':
        return 'psychology';
      case 'query':
        return 'search';
      case 'search':
        return 'manage_search';
      case 'result':
        return 'fact_check';
      case 'summary':
        return 'summarize';
      case 'complete':
        return 'done_all';
      case 'warning':
        return 'warning';
      case 'error':
        return 'error';
      default:
        return 'arrow_right';
    }
  };

  return (
    <div className="agent-info-container">
      {agentInfo.notes_added !== undefined && (
        <div className="agent-activity-info">
          <svg
            className="agent-icon"
            xmlns="http://www.w3.org/2000/svg"
            height="16"
            width="16"
            viewBox="0 0 512 512"
          >
            <path
              fill="currentColor"
              d="M256 0c4.6 0 9.2 1 13.4 2.9L457.7 82.8c22 9.3 38.4 31 38.3 57.2c-.5 99.2-41.3 280.7-213.7 363c-16.7 8-36.1 8-52.8 0C57.3 420.7 16.5 239.2 16 140c-.1-26.2 16.3-47.9 38.3-57.2L242.7 2.9C246.8 1 251.4 0 256 0z"
            />
          </svg>
          <span>
            AI Agent found {agentInfo.notes_added} additional{' '}
            {agentInfo.notes_added === 1 ? 'note' : 'notes'} to help answer your question
          </span>
        </div>
      )}

      {agentInfo.error && (
        <div className="agent-error-info">
          <svg
            className="agent-error-icon"
            xmlns="http://www.w3.org/2000/svg"
            height="16"
            width="16"
            viewBox="0 0 512 512"
          >
            <path
              fill="currentColor"
              d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zm0-384c13.3 0 24 10.7 24 24V264c0 13.3-10.7 24-24 24s-24-10.7-24-24V152c0-13.3 10.7-24 24-24zM224 352a32 32 0 1 1 64 0 32 32 0 1 1 -64 0z"
            />
          </svg>
          <span>AI Agent error: {agentInfo.error}</span>
        </div>
      )}

      {/* Actions toggle button - only show if there are actions */}
      {agentInfo.actions && agentInfo.actions.length > 0 && (
        <div className="agent-actions-container">
          <button
            onClick={toggleActions}
            className="agent-actions-toggle"
            aria-expanded={showActions}
          >
            <span className="material-icons">{showActions ? 'expand_less' : 'expand_more'}</span>
            {showActions ? 'Hide agent actions' : 'Show agent actions'}
          </button>

          {/* Actions list */}
          {showActions && (
            <div className="agent-actions-list">
              <h4>Agent Actions:</h4>
              <ol className="actions-timeline">
                {agentInfo.actions.map((action, index) => (
                  <li key={index} className={`action-item action-type-${action.type}`}>
                    <span className="material-icons action-icon">{getActionIcon(action.type)}</span>
                    <span className="action-description">{action.description}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AgentInfo;
