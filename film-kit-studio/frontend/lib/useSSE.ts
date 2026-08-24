// ── SSE (Server-Sent Events) hook for task progress ────────

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { SSEEvent } from './types';

interface UseSSEOptions {
  onProgress?: (progress: number, message: string) => void;
  onSceneUpdate?: (data: Record<string, unknown>) => void;
  onCompleted?: (result: Record<string, unknown>) => void;
  onError?: (message: string) => void;
}

export function useSSE(taskId: string | null, options: UseSSEOptions = {}) {
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const connect = useCallback((id: string) => {
    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const url = `/api/pipeline/tasks/${id}/events`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data);
      optionsRef.current.onProgress?.(data.progress, data.message);
    });

    es.addEventListener('scene_update', (e) => {
      const data = JSON.parse(e.data);
      optionsRef.current.onSceneUpdate?.(data);
    });

    es.addEventListener('completed', (e) => {
      const data = JSON.parse(e.data);
      optionsRef.current.onCompleted?.(data.result);
      es.close();
      setConnected(false);
    });

    es.addEventListener('error', (e) => {
      // SSE 'error' event from server (custom event named 'error')
      try {
        const data = JSON.parse((e as MessageEvent).data);
        optionsRef.current.onError?.(data.message);
      } catch {
        optionsRef.current.onError?.('Task failed');
      }
      es.close();
      setConnected(false);
    });
  }, []);

  useEffect(() => {
    if (taskId) {
      connect(taskId);
    }
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [taskId, connect]);

  return { connected };
}
