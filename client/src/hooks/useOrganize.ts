import { useState, useCallback, useRef } from 'react';

import { API_ROUTES } from '@/const';
import {
  TagProposal,
  ProposalAction,
  ProposalState,
  Granularity,
  CategorizationProgress,
} from '@/types';

interface StreamProgressMessage {
  type: 'progress';
  stage: string;
  message: string;
  progress: number;
  current?: number;
  total?: number;
}

interface StreamProposalsMessage {
  type: 'proposals';
  proposals: TagProposal[];
}

interface StreamDoneMessage {
  type: 'done';
}

interface StreamErrorMessage {
  type: 'error';
  error: string;
}

type StreamMessage =
  | StreamProgressMessage
  | StreamProposalsMessage
  | StreamDoneMessage
  | StreamErrorMessage;

export const useOrganize = () => {
  const [granularity, setGranularity] = useState<Granularity>('broad');
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState<CategorizationProgress | null>(null);
  const [proposals, setProposals] = useState<ProposalState[]>([]);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const startCategorization = useCallback(async () => {
    setIsProcessing(true);
    setError(null);
    setProposals([]);
    setProgress(null);

    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(API_ROUTES.ORGANIZE_CATEGORIZE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ granularity }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('ReadableStream not supported');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) {
            continue;
          }

          try {
            const data: StreamMessage = JSON.parse(trimmed);

            switch (data.type) {
              case 'progress':
                setProgress({
                  stage: data.stage,
                  message: data.message,
                  progress: data.progress,
                  current: data.current,
                  total: data.total,
                });
                break;

              case 'proposals':
                setProposals(
                  data.proposals.map((p) => ({
                    proposal: p,
                    action: 'pending' as ProposalAction,
                  })),
                );
                break;

              case 'done':
                break;

              case 'error':
                setError(data.error);
                break;
            }
          } catch {
            // eslint-disable-next-line no-console
            console.error('Error parsing stream chunk:', trimmed);
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError(`Error: ${(err as Error).message}`);
        // eslint-disable-next-line no-console
        console.error('Categorization error:', err);
      }
    } finally {
      abortControllerRef.current = null;
      setIsProcessing(false);
    }
  }, [granularity]);

  const cancelCategorization = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsProcessing(false);
      setProgress(null);
    }
  }, []);

  const updateProposal = useCallback((index: number, updates: Partial<ProposalState>) => {
    setProposals((prev) => prev.map((p, i) => (i === index ? { ...p, ...updates } : p)));
  }, []);

  const approveProposal = useCallback(
    (index: number) => {
      updateProposal(index, { action: 'approve' });
    },
    [updateProposal],
  );

  const rejectProposal = useCallback(
    (index: number) => {
      updateProposal(index, { action: 'reject' });
    },
    [updateProposal],
  );

  const renameProposal = useCallback(
    (index: number, newName: string) => {
      updateProposal(index, { action: 'rename', newName });
    },
    [updateProposal],
  );

  const mergeProposals = useCallback((sourceIndex: number, targetIndex: number) => {
    setProposals((prev) => {
      const updated = [...prev];
      const targetName = updated[targetIndex].proposal.tag_name;
      updated[sourceIndex] = {
        ...updated[sourceIndex],
        action: 'merge',
        mergeTarget: targetName,
      };
      return updated;
    });
  }, []);

  const approveAll = useCallback(() => {
    setProposals((prev) =>
      prev.map((p) => (p.action === 'pending' ? { ...p, action: 'approve' as ProposalAction } : p)),
    );
  }, []);

  const resetProposals = useCallback(() => {
    setProposals((prev) => prev.map((p) => ({ ...p, action: 'pending' as ProposalAction })));
  }, []);

  const applyProposals = useCallback(async () => {
    const actionable = proposals.filter((p) => p.action !== 'pending' && p.action !== 'reject');

    if (actionable.length === 0) {
      return;
    }

    setIsApplying(true);
    setError(null);

    try {
      const actions = actionable.map((p) => ({
        action: p.action === 'rename' ? 'rename' : p.action === 'merge' ? 'merge' : 'approve',
        tag_name: p.proposal.tag_name,
        note_ids: p.proposal.note_ids,
        new_name: p.action === 'rename' ? p.newName : undefined,
      }));

      const response = await fetch(API_ROUTES.ORGANIZE_APPLY, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actions }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const result = await response.json();
      setProposals([]);
      setProgress(null);
      return result;
    } catch (err) {
      setError(`Failed to apply tags: ${(err as Error).message}`);
      // eslint-disable-next-line no-console
      console.error('Apply error:', err);
    } finally {
      setIsApplying(false);
    }
  }, [proposals]);

  const actionablCount = proposals.filter(
    (p) => p.action !== 'pending' && p.action !== 'reject',
  ).length;

  const hasProposals = proposals.length > 0;

  return {
    granularity,
    setGranularity,
    isProcessing,
    progress,
    proposals,
    isApplying,
    error,
    hasProposals,
    actionablCount,
    startCategorization,
    cancelCategorization,
    approveProposal,
    rejectProposal,
    renameProposal,
    mergeProposals,
    approveAll,
    resetProposals,
    applyProposals,
  };
};
