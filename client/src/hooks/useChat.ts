import { useState, useEffect, useCallback, useRef } from 'react';

import { API_ROUTES } from '@/const';
import { Citation, ChatSessionSummary, GroundedCitation, GroundedContext, Note } from '@/types';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: number;
  /** Legacy citations. */
  citations?: Citation[];
  /** New grounded citations with character offsets. */
  groundedCitations?: GroundedCitation[];
}

// New incremental streaming protocol types
interface StreamContextMessage {
  type: 'context';
  items: GroundedContext[];
  intent: string;
  session_id: string;
  total_notes: number;
  /** Legacy flat notes list for backward compatibility. */
  notes: Note[];
}

interface StreamDeltaMessage {
  type: 'delta';
  content: string;
}

interface StreamDoneMessage {
  type: 'done';
  citations: GroundedCitation[];
  full_response: string;
}

interface StreamErrorMessage {
  type: 'error';
  error: string;
}

type StreamMessage =
  | StreamContextMessage
  | StreamDeltaMessage
  | StreamDoneMessage
  | StreamErrorMessage;

export const useChat = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [relevantNotes, setRelevantNotes] = useState<Note[]>([]);
  const [modelName, setModelName] = useState<string | null>(null);
  const [useNotesContext, setUseNotesContext] = useState<boolean>(true);
  const [topic, setTopic] = useState<string>('');

  // Grounded context state
  const [contextItems, setContextItems] = useState<GroundedContext[]>([]);
  const [retrievalIntent, setRetrievalIntent] = useState<string>('factual');
  const [totalNotes, setTotalNotes] = useState<number>(0);

  // Document viewer state
  const [activeCitationId, setActiveCitationId] = useState<string | null>(null);
  const [activeDocument, setActiveDocument] = useState<{
    noteId: string;
    noteTitle: string;
    noteContent: string;
    context: GroundedContext | null;
  } | null>(null);

  // Session state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch the model name on mount
  useEffect(() => {
    const fetchModelInfo = async () => {
      try {
        const response = await fetch(API_ROUTES.CHAT_MODEL);
        const data = await response.json();
        setModelName(data.model);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('Error fetching model info:', err);
      }
    };

    fetchModelInfo();
  }, []);

  // Load sessions on mount
  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = useCallback(async () => {
    try {
      const response = await fetch(API_ROUTES.CHAT_SESSIONS);
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Error fetching sessions:', err);
    }
  }, []);

  const createSession = useCallback(async (): Promise<string | null> => {
    try {
      const response = await fetch(API_ROUTES.CHAT_SESSIONS, { method: 'POST' });
      const data = await response.json();
      setSessionId(data.id);
      await fetchSessions();
      return data.id;
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Error creating session:', err);
      return null;
    }
  }, [fetchSessions]);

  const loadSession = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${API_ROUTES.CHAT_SESSIONS}/${id}`);
      if (!response.ok) return;
      const data = await response.json();
      setSessionId(data.id);
      setMessages(
        (data.messages || []).map((m: { role: string; content: string }) => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
        })),
      );
      setRelevantNotes([]);
      setContextItems([]);
      setActiveDocument(null);
      setActiveCitationId(null);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Error loading session:', err);
    }
  }, []);

  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await fetch(`${API_ROUTES.CHAT_SESSIONS}/${id}`, { method: 'DELETE' });
        if (sessionId === id) {
          setSessionId(null);
          setMessages([]);
          setRelevantNotes([]);
          setContextItems([]);
          setActiveDocument(null);
          setActiveCitationId(null);
        }
        await fetchSessions();
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('Error deleting session:', err);
      }
    },
    [sessionId, fetchSessions],
  );

  const renameSession = useCallback(
    async (id: string, title: string) => {
      try {
        await fetch(`${API_ROUTES.CHAT_SESSIONS}/${id}?title=${encodeURIComponent(title)}`, {
          method: 'PATCH',
        });
        await fetchSessions();
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('Error renaming session:', err);
      }
    },
    [fetchSessions],
  );

  const saveSessionMessages = useCallback(
    async (sid: string, msgs: ChatMessage[]) => {
      try {
        await fetch(`${API_ROUTES.CHAT_SESSIONS}/${sid}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: msgs.map(({ role, content }) => ({ role, content })),
          }),
        });
        await fetchSessions();
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('Error saving session messages:', err);
      }
    },
    [fetchSessions],
  );

  const stopGenerating = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  }, []);

  /**
   * Open the document viewer for a specific citation.
   */
  const openDocumentViewer = useCallback(
    (citationId: string) => {
      setActiveCitationId(citationId);

      // Find the matching context item
      const ctx = contextItems.find((c) => c.citation_id === citationId);
      if (!ctx) return;

      // Find the full note content from relevantNotes
      const note = relevantNotes.find((n) => n.id === ctx.note_id);
      setActiveDocument({
        noteId: ctx.note_id,
        noteTitle: ctx.note_title,
        noteContent: note?.content || ctx.text,
        context: ctx,
      });
    },
    [contextItems, relevantNotes],
  );

  const closeDocumentViewer = useCallback(() => {
    setActiveDocument(null);
    setActiveCitationId(null);
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) {
        return;
      }

      // Auto-create session if none exists
      let currentSessionId = sessionId;
      if (!currentSessionId) {
        currentSessionId = await createSession();
      }

      // Add user message
      const userMessage: ChatMessage = {
        role: 'user',
        content,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setError(null);

      // Create a placeholder for the assistant's response
      const assistantMessageId = Date.now() + 1;
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: assistantMessageId,
      };

      setMessages((prev) => [...prev, assistantMessage]);

      // Prepare request data
      const payload = {
        messages: [...messages, userMessage].map(({ role, content }) => ({ role, content })),
        stream: true,
        useNotesContext,
        topic: topic.trim() || undefined,
        session_id: currentSessionId || undefined,
      };

      // Stop any existing stream
      stopGenerating();
      abortControllerRef.current = new AbortController();

      try {
        const response = await fetch(API_ROUTES.CHAT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('ReadableStream not supported');
        }

        let accumulatedContent = '';
        const decoder = new TextDecoder();
        let buffer = '';

        // Process the stream with new protocol
        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          // Keep the last (potentially incomplete) line in the buffer
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;

            try {
              const data: StreamMessage = JSON.parse(trimmed);

              switch (data.type) {
                case 'context': {
                  // Store grounded context items
                  if (data.items && data.items.length > 0) {
                    setContextItems(data.items);
                  }
                  if (data.intent) {
                    setRetrievalIntent(data.intent);
                  }
                  if (data.total_notes) {
                    setTotalNotes(data.total_notes);
                  }
                  // Legacy: also set notes for backward compat
                  if (data.notes && data.notes.length > 0) {
                    setRelevantNotes(data.notes);
                  }
                  break;
                }

                case 'delta':
                  // Incremental content token
                  accumulatedContent += data.content;
                  setMessages((prevMessages) =>
                    prevMessages.map((msg) =>
                      msg.timestamp === assistantMessageId && msg.role === 'assistant'
                        ? { ...msg, content: accumulatedContent }
                        : msg,
                    ),
                  );
                  break;

                case 'done':
                  // Final message with grounded citations
                  setMessages((prevMessages) =>
                    prevMessages.map((msg) =>
                      msg.timestamp === assistantMessageId && msg.role === 'assistant'
                        ? {
                            ...msg,
                            content: data.full_response || accumulatedContent,
                            groundedCitations: data.citations,
                          }
                        : msg,
                    ),
                  );
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

        // Save session after completion
        if (currentSessionId) {
          const finalMessages: ChatMessage[] = [];
          setMessages((prev) => {
            finalMessages.push(...prev);
            return prev;
          });
          // Use a small delay to ensure state is settled
          setTimeout(() => {
            setMessages((currentMsgs) => {
              saveSessionMessages(currentSessionId!, currentMsgs);
              return currentMsgs;
            });
          }, 100);
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setError(`Error: ${(err as Error).message}`);
          // eslint-disable-next-line no-console
          console.error('Chat error:', err);
        }
      } finally {
        abortControllerRef.current = null;
        setIsLoading(false);
      }
    },
    [messages, stopGenerating, useNotesContext, topic, sessionId, createSession, saveSessionMessages],
  );

  const clearChat = useCallback(() => {
    stopGenerating();
    setSessionId(null);
    setMessages([]);
    setRelevantNotes([]);
    setContextItems([]);
    setActiveDocument(null);
    setActiveCitationId(null);
    setError(null);
  }, [stopGenerating]);

  const newChat = useCallback(() => {
    stopGenerating();
    setSessionId(null);
    setMessages([]);
    setRelevantNotes([]);
    setContextItems([]);
    setActiveDocument(null);
    setActiveCitationId(null);
    setError(null);
  }, [stopGenerating]);

  const toggleNotesContext = useCallback(() => {
    setUseNotesContext((prev) => !prev);
  }, []);

  return {
    messages,
    isLoading,
    error,
    relevantNotes,
    modelName,
    useNotesContext,
    topic,
    setTopic,
    sendMessage,
    clearChat,
    stopGenerating,
    toggleNotesContext,
    // Session management
    sessionId,
    sessions,
    newChat,
    loadSession,
    deleteSession,
    renameSession,
    fetchSessions,
    // Grounded context
    contextItems,
    retrievalIntent,
    totalNotes,
    // Document viewer
    activeCitationId,
    activeDocument,
    openDocumentViewer,
    closeDocumentViewer,
  };
};
