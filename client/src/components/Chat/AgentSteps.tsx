import { AgentStep } from '@/types';

import './styles.css';

interface AgentStepsProps {
  steps: AgentStep[];
  isActive: boolean;
}

const ACTION_CONFIG: Record<string, { icon: string; label: string }> = {
  search_notes: { icon: 'search', label: 'Searching notes' },
  search_chunks: { icon: 'find_in_page', label: 'Searching chunks' },
  filter_by_tag: { icon: 'label', label: 'Filtering by tag' },
  evaluate_coverage: { icon: 'checklist', label: 'Evaluating coverage' },
  respond: { icon: 'check_circle', label: 'Context gathering complete' },
};

const getActionConfig = (action: string) =>
  ACTION_CONFIG[action] || { icon: 'smart_toy', label: action };

const formatParams = (action: string, params: Record<string, unknown>): string => {
  if (action === 'search_notes' || action === 'search_chunks') {
    return params.query ? `"${params.query}"` : '';
  }
  if (action === 'filter_by_tag') {
    return params.tag ? `#${params.tag}` : '';
  }
  if (action === 'respond') {
    return '';
  }
  return '';
};

export const AgentSteps = ({ steps, isActive }: AgentStepsProps) => {
  if (steps.length === 0) {
    return null;
  }

  return (
    <div className="agent-steps">
      <div className="agent-steps-header">
        <span className="material-icons agent-header-icon">psychology</span>
        <span className="agent-header-text">Agent Retrieval</span>
      </div>
      <div className="agent-timeline">
        {steps.map((step, idx) => {
          const config = getActionConfig(step.action);
          const paramText = formatParams(step.action, step.params);
          const isLast = idx === steps.length - 1;
          const isPending = isLast && isActive && step.action !== 'respond';

          return (
            <div
              key={step.step_number}
              className={`agent-step ${isPending ? 'agent-step-active' : 'agent-step-done'}`}
            >
              <div className="agent-step-indicator">
                <span className={`material-icons agent-step-icon ${isPending ? 'pulsing' : ''}`}>
                  {config.icon}
                </span>
                {idx < steps.length - 1 && <div className="agent-step-line" />}
              </div>
              <div className="agent-step-content">
                <div className="agent-step-action">
                  {config.label}
                  {paramText && <span className="agent-step-params">{paramText}</span>}
                </div>
                {step.result_summary && (
                  <div className="agent-step-result">{step.result_summary}</div>
                )}
                {step.notes_found > 0 && (
                  <span className="agent-step-badge">+{step.notes_found} notes</span>
                )}
              </div>
            </div>
          );
        })}
        {isActive && steps[steps.length - 1]?.action !== 'respond' && (
          <div className="agent-step agent-step-active">
            <div className="agent-step-indicator">
              <span className="material-icons agent-step-icon pulsing">more_horiz</span>
            </div>
            <div className="agent-step-content">
              <div className="agent-step-action">Thinking...</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
