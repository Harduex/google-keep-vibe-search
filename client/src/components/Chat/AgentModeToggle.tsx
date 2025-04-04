import React from 'react';

interface AgentModeToggleProps {
  agentEnabled: boolean;
  useAgentMode: boolean;
  toggleAgentMode: () => void;
  isLoading: boolean;
}

export const AgentModeToggle: React.FC<AgentModeToggleProps> = ({
  agentEnabled,
  useAgentMode,
  toggleAgentMode,
  isLoading,
}) => {
  // If agent functionality is not enabled at all, don't show the toggle
  if (!agentEnabled) {
    return null;
  }

  return (
    <div className="notes-toggle">
      <label
        className="toggle-label"
        title="When enabled, the AI can autonomously search for additional information if needed"
      >
        <input
          type="checkbox"
          checked={useAgentMode}
          onChange={toggleAgentMode}
          disabled={isLoading}
        />
        <span className="toggle-slider"></span>
        <span className="toggle-text">
          <span className="material-icons">smart_toy</span>
          AI Agent Mode
        </span>
      </label>
    </div>
  );
};

export default AgentModeToggle;
