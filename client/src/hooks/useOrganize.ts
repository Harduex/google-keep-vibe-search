import { useState, useCallback, useEffect, useRef } from 'react';

import { API_ROUTES } from '@/const';
import {
  TagProposal,
  ProposalAction,
  ProposalState,
  Granularity,
  CategorizationProgress,
  isInfoProposal,
  isMergeProposal,
  isAssignProposal,
} from '@/types';

export interface ApplyActionPayload {
  action: string;
  tag_name?: string;
  note_ids?: string[];
  new_name?: string;
  source_tag?: string;
  target_tag?: string;
  note_id?: string;
  tag?: string;
}

/** Build the /apply payload for one staged proposal, or null if not actionable. */
export const buildApplyAction = (state: ProposalState): ApplyActionPayload | null => {
  const { proposal, action, newName } = state;
  if (action === 'pending' || action === 'reject' || isInfoProposal(proposal)) {
    return null;
  }

  if (isMergeProposal(proposal)) {
    return {
      action: 'merge_tags',
      source_tag: proposal.source_tag,
      target_tag: proposal.target_tag,
    };
  }

  if (isAssignProposal(proposal)) {
    return { action: 'assign_tag', note_id: proposal.note_id, tag: proposal.tag };
  }

  if (action === 'merge') {
    // A classic proposal staged for merge carries `mergeTarget` (set by `mergeProposals`
    // from the target proposal's tag_name). If it's missing there is nothing to merge
    // into, so drop the action rather than falling back to "approve", which would tag the
    // notes with their own name.
    //
    // Merging a *proposal* means "tag this cluster's notes with the target name" — so it
    // is an approve under the target's name, not `merge_tags`. `merge_tags` renames a tag
    // that is already applied; a proposal's tag never is, so emitting it here made
    // rename_tag raise KeyError and the route skip the action, leaving the notes untagged
    // and reporting "Applied 0 tags to 0 notes". `merge_tags` stays correct for gray-zone
    // merge proposals (handled above), where both tags really do exist on disk.
    if (!state.mergeTarget) {
      return null;
    }
    return {
      action: 'approve',
      tag_name: state.mergeTarget,
      note_ids: proposal.note_ids,
    };
  }

  // Classic cluster tag proposal (approve / rename).
  return {
    action: action === 'rename' ? 'rename' : 'approve',
    tag_name: proposal.tag_name,
    note_ids: proposal.note_ids,
    new_name: action === 'rename' ? newName : undefined,
  };
};

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

interface StreamProposalMessage {
  // One named cluster, streamed as soon as its name exists so the user can review while
  // naming continues. The payload matches one element of a `proposals` array, so the same
  // renderer handles it. `current`/`total` are the naming progress (cluster i of N).
  type: 'proposal';
  proposal: TagProposal;
  current: number;
  total: number;
}

interface StreamDoneMessage {
  type: 'done';
}

interface StreamErrorMessage {
  type: 'error';
  error: string;
}

interface StreamLabelUpdatesMessage {
  type: 'label_updates';
  proposals: TagProposal[];
}

type StreamMessage =
  | StreamProgressMessage
  | StreamProposalsMessage
  | StreamProposalMessage
  | StreamLabelUpdatesMessage
  | StreamDoneMessage
  | StreamErrorMessage;

/** Map of tag name -> staged action, the shape PUT /pending/actions expects. */
type StagedActions = Record<string, ProposalAction>;

/**
 * Build the staged-actions map from the current proposal states.
 * Keyed by the proposal's tag name — unique within a vocabulary — so the server's lock
 * list (which keys on tag names) and the client's staged state stay aligned even as the
 * list grows underneath the user.
 */
const toActionsMap = (states: ProposalState[]): StagedActions => {
  const out: StagedActions = {};
  for (const s of states) {
    if (s.action === 'pending') {
      continue;
    }
    // Info/dashboard proposals have no tag_name and are not actionable in a way the
    // consolidation lock cares about; skip them so the lock list stays tag-keyed.
    if (isInfoProposal(s.proposal) || !s.proposal.tag_name) {
      continue;
    }
    out[s.proposal.tag_name] = s.action;
  }
  return out;
};

/** The debounced-PUT window. Long enough to coalesce a rapid burst of decisions, short
 * enough that a staged decision reaches the server (and enters the lock list) well before
 * consolidation runs. */
const ACTIONS_DEBOUNCE_MS = 400;

export const useOrganize = () => {
  const [granularity, setGranularity] = useState<Granularity>('broad');
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState<CategorizationProgress | null>(null);
  const [proposals, setProposals] = useState<ProposalState[]>([]);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [restoredAt, setRestoredAt] = useState<number | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Keep the latest staged decisions in a ref so the debounced PUT (a setInterval-free
  // timeout callback) always reads current state without re-subscribing on every change.
  const stagedActionsRef = useRef<StagedActions>({});
  const actionsTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * Debounced-upload the staged decisions to the server, where they enter the lock list.
   * The server's consolidation step skips any tag the user has acted on (both as a merge
   * source and a merge target), so nothing the user decided mid-run can be undone by the
   * machine. Fire-and-forget: the local state is the source of truth for the UI; the PUT
   * just crash-proofs the lock list. Never blocks an interaction on a network round-trip.
   */
  const persistStagedActions = useCallback(() => {
    if (actionsTimerRef.current) {
      clearTimeout(actionsTimerRef.current);
    }
    actionsTimerRef.current = setTimeout(() => {
      const actions = stagedActionsRef.current;
      // Send even when empty: clearing the last staged decision must propagate so a
      // subsequent consolidation does not keep a stale lock. Shallow copy so the body is a
      // plain JSON object, not a live ref.
      fetch(`${API_ROUTES.ORGANIZE_PENDING}/actions`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actions }),
      }).catch(() => {
        // The local list still holds the decision; the server just will not lock against
        // it. Better than blocking the user on a retry.
      });
    }, ACTIONS_DEBOUNCE_MS);
  }, []);

  /** Record a staged decision in the ref + schedule the debounced PUT. */
  const stageDecision = useCallback(
    (mutator: (prev: ProposalState[]) => ProposalState[]) => {
      setProposals((prev) => {
        const next = mutator(prev);
        stagedActionsRef.current = toActionsMap(next);
        return next;
      });
      persistStagedActions();
    },
    [persistStagedActions],
  );

  /**
   * Re-attach previously staged decisions to a fresh proposal list, by tag name. Used at
   * two points: when the authoritative end-of-run frame replaces the growing list (so a
   * decision the user made on cluster X survives the final consolidation that may have
   * renamed neighbours), and when the tab remounts and restores from the persisted
   * artifact. Tag-name keyed because the list can change shape/order under the user.
   */
  const reattachActions = (
    fresh: TagProposal[],
    staged: StagedActions,
    extra: Partial<Record<string, ProposalState>> = {},
  ): ProposalState[] =>
    fresh.map((p) => {
      const name = p.tag_name;
      if (name && staged[name] && staged[name] !== 'pending') {
        return { proposal: p, action: staged[name], ...extra[name] };
      }
      return { proposal: p, action: 'pending' as ProposalAction };
    });

  // Proposals cost one LLM call per cluster, so the server persists them as soon as they
  // are generated. Pick any unapplied set back up on mount: a reload, a dev-server restart
  // or a crash no longer throws the expensive part away. Staged decisions are restored
  // alongside the proposals (item 7), so the review state survives a remount too.
  useEffect(() => {
    let cancelled = false;
    const restorePending = async () => {
      try {
        const response = await fetch(API_ROUTES.ORGANIZE_PENDING);
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        if (cancelled || !data?.proposals?.length) {
          return;
        }
        const staged: StagedActions =
          data.actions && typeof data.actions === 'object' ? data.actions : {};
        setProposals((prev) => (prev.length > 0 ? prev : reattachActions(data.proposals, staged)));
        stagedActionsRef.current = staged;
        setRestoredAt(data.generated_at ?? null);
      } catch {
        // Nothing to restore is the normal case; never block the tab on it.
      }
    };
    restorePending();
    return () => {
      cancelled = true;
      if (actionsTimerRef.current) {
        clearTimeout(actionsTimerRef.current);
      }
    };
  }, []);

  const discardProposals = useCallback(async () => {
    setProposals([]);
    setProgress(null);
    setRestoredAt(null);
    stagedActionsRef.current = {};
    try {
      await fetch(API_ROUTES.ORGANIZE_PENDING, { method: 'DELETE' });
    } catch {
      // The local list is already cleared; the stale file is harmless and gets replaced.
    }
  }, []);

  const startCategorization = useCallback(async () => {
    setIsProcessing(true);
    setError(null);
    setProposals([]);
    stagedActionsRef.current = {};
    setProgress(null);

    abortControllerRef.current = new AbortController();

    // Snapshot the staged decisions at the start of the run. A new run discards the
    // previous vocabulary, so old staged actions no longer correspond to any tag — but we
    // clear the server-side lock list too, so consolidation starts clean.
    fetch(`${API_ROUTES.ORGANIZE_PENDING}/actions`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actions: {} }),
    }).catch(() => {
      /* non-fatal: a stale lock list just means the first consolidation is unconstrained */
    });

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

      // The staged snapshot used to re-attach decisions across the authoritative
      // end-of-run frame. Held outside React state so the streaming loop can read it
      // without re-subscribing, and updated whenever the user stages a decision.
      const stagedSnapshot = () => stagedActionsRef.current;

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

              case 'proposal': {
                // One named cluster arrives — append it in arrival order (no re-sort).
                // Naming is size-descending, so the most important clusters come first;
                // a list that re-sorts while the user works in it moves cards under the
                // cursor. Show as pending until the user decides.
                setProposals((prev) => [...prev, { proposal: data.proposal, action: 'pending' }]);
                // The frame carries the most up-to-date naming progress (current of total);
                // mirror it into the progress state so the progress bar advances per cluster
                // even between the coarser `progress` frames.
                if (typeof data.current === 'number' && typeof data.total === 'number') {
                  setProgress((prev) => {
                    if (prev) {
                      return { ...prev, current: data.current, total: data.total };
                    }
                    return {
                      stage: 'naming',
                      message: `Named ${data.current} of ${data.total}`,
                      progress: data.total > 0 ? data.current / data.total : 0,
                      current: data.current,
                      total: data.total,
                    };
                  });
                }
                break;
              }

              case 'label_updates':
              case 'proposals': {
                // The authoritative end-of-run frame replaces the growing list for
                // everything *unlocked*, but re-attaches the user's staged decisions by
                // tag name (item 4) — a decision on cluster X must survive the final
                // consolidation that may have renamed or merged its neighbours.
                const staged = stagedSnapshot();
                setProposals(reattachActions(data.proposals, staged));
                break;
              }

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

  /**
   * Resolve a ProposalState by an identifier that is either a tag name (classic proposals —
   * the streaming list grows underneath the user, so an index would shift) or an array
   * index (dashboard cards: info/merge/assign arrive together at the end of the run, so an
   * index is stable for them). Classic cards pass their tag_name; dashboard cards pass
   * their numeric index. Tag name is matched first so a classic card is never confused with
   * a positional lookup.
   */
  const resolveById = useCallback((states: ProposalState[], id: string | number): number => {
    if (typeof id === 'string') {
      const byName = states.findIndex((s) => s.proposal.tag_name === id);
      if (byName !== -1) {
        return byName;
      }
    }
    const asNum = typeof id === 'number' ? id : Number(id);
    if (Number.isInteger(asNum) && asNum >= 0 && asNum < states.length) {
      return asNum;
    }
    return -1;
  }, []);

  const approveProposal = useCallback(
    (id: string | number) => {
      stageDecision((prev) => {
        const idx = resolveById(prev, id);
        if (idx === -1) {
          return prev;
        }
        return prev.map((p, i) => (i === idx ? { ...p, action: 'approve' } : p));
      });
    },
    [stageDecision, resolveById],
  );

  const rejectProposal = useCallback(
    (id: string | number) => {
      stageDecision((prev) => {
        const idx = resolveById(prev, id);
        if (idx === -1) {
          return prev;
        }
        return prev.map((p, i) => (i === idx ? { ...p, action: 'reject' } : p));
      });
    },
    [stageDecision, resolveById],
  );

  const renameProposal = useCallback(
    (id: string | number, newName: string) => {
      stageDecision((prev) => {
        const idx = resolveById(prev, id);
        if (idx === -1) {
          return prev;
        }
        return prev.map((p, i) => (i === idx ? { ...p, action: 'rename', newName } : p));
      });
    },
    [stageDecision, resolveById],
  );

  const mergeProposals = useCallback(
    // Keyed by tag name (item 6): a staged merge records the target's tag_name, which is
    // stable as the list grows, instead of a positional index that shifts when more
    // proposals arrive. Both arguments are tag names — classic proposals only, since
    // dashboard cards have no tag_name and are never merge sources/targets.
    (sourceTagName: string, targetTagName: string) => {
      stageDecision((prev) => {
        const target = prev.find(
          (s) =>
            s.proposal.tag_name === targetTagName &&
            !isInfoProposal(s.proposal) &&
            !isMergeProposal(s.proposal) &&
            !isAssignProposal(s.proposal),
        );
        if (!target) {
          return prev;
        }
        return prev.map((p) =>
          p.proposal.tag_name === sourceTagName
            ? { ...p, action: 'merge', mergeTarget: target.proposal.tag_name }
            : p,
        );
      });
    },
    [stageDecision],
  );

  const approveAll = useCallback(() => {
    stageDecision((prev) =>
      prev.map((p) =>
        p.action === 'pending' && !isInfoProposal(p.proposal)
          ? { ...p, action: 'approve' as ProposalAction }
          : p,
      ),
    );
  }, [stageDecision]);

  const resetProposals = useCallback(() => {
    stageDecision((prev) => prev.map((p) => ({ ...p, action: 'pending' as ProposalAction })));
  }, [stageDecision]);

  const applyProposals = useCallback(async () => {
    // Read current state via a functional snapshot so we always apply exactly what the
    // user sees, even if a debounced PUT is in flight.
    const current = proposals;
    const actions = current
      .map(buildApplyAction)
      .filter((a): a is ApplyActionPayload => a !== null);

    if (actions.length === 0) {
      return;
    }

    setIsApplying(true);
    setError(null);

    try {
      const response = await fetch(API_ROUTES.ORGANIZE_APPLY, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actions }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const result = await response.json();

      // Only clear the list when something was actually applied. Clearing unconditionally is
      // how an apply that tagged nothing — a rejected action, or a bug that skipped it
      // server-side — threw away a generation that had cost hundreds of LLM calls.
      const applied = (result?.notes_tagged || 0) > 0 || (result?.tags_created || 0) > 0;
      if (applied) {
        setProposals([]);
        setProgress(null);
        stagedActionsRef.current = {};
      } else {
        setError(
          'Nothing was applied, so your proposals have been kept. ' +
            (result?.message || 'No tags were created.'),
        );
      }
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
    (p) => p.action !== 'pending' && p.action !== 'reject' && !isInfoProposal(p.proposal),
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
    restoredAt,
    discardProposals,
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
