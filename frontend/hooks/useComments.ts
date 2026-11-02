/**
 * Real-time Comments & Annotations Hook
 * React hook for managing collaborative comments and annotations on documents
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useAuth } from './useAuth';
import { useRealtime } from './useRealtime';

interface Comment {
  id: string;
  threadId: string;
  parentId?: string;
  documentId: string;
  anchor: {
    // For text documents
    position?: number;
    length?: number;
    // For spreadsheets/grids
    cell?: string;
    // For whiteboards
    x?: number;
    y?: number;
    width?: number;
    height?: number;
  };
  authorId: string;
  authorName: string;
  authorColor: string;
  content: string;
  createdAt: number;
  updatedAt: number;
  resolved: boolean;
  reactions: Record<string, string[]>; // emoji -> userIds[]
  mentions: string[]; // userIds mentioned
  attachments: Array<{
    id: string;
    name: string;
    url: string;
    type: string;
    size: number;
  }>;
}

interface CommentThread {
  id: string;
  documentId: string;
  anchor: Comment['anchor'];
  comments: Comment[];
  resolved: boolean;
  createdAt: number;
  updatedAt: number;
  createdBy: string;
  assignedTo?: string;
  labels: string[];
}

interface UseCommentsOptions {
  documentId: string;
  organizationId: string;
  autoConnect?: boolean;
  onCommentChange?: (threads: CommentThread[]) => void;
}

interface UseCommentsReturn {
  threads: CommentThread[];
  loading: boolean;
  error: string | null;
  // Thread operations
  createThread: (anchor: CommentThread['anchor'], initialComment: string) => Promise<CommentThread>;
  deleteThread: (threadId: string) => Promise<void>;
  resolveThread: (threadId: string) => Promise<void>;
  reopenThread: (threadId: string) => Promise<void>;
  assignThread: (threadId: string, userId: string) => Promise<void>;
  addLabel: (threadId: string, label: string) => Promise<void>;
  removeLabel: (threadId: string, label: string) => Promise<void>;
  // Comment operations
  addComment: (threadId: string, content: string, parentId?: string) => Promise<Comment>;
  updateComment: (threadId: string, commentId: string, content: string) => Promise<void>;
  deleteComment: (threadId: string, commentId: string) => Promise<void>;
  reactToComment: (threadId: string, commentId: string, emoji: string) => Promise<void>;
  removeReaction: (threadId: string, commentId: string, emoji: string) => Promise<void>;
  mentionUser: (threadId: string, commentId: string, userId: string) => Promise<void>;
  // Real-time
  subscribe: () => void;
  unsubscribe: () => void;
}

export function useComments(options: UseCommentsOptions): UseCommentsReturn {
  const { documentId, organizationId, autoConnect = true, onCommentChange } = options;
  const { user, accessToken } = useAuth();
  const { send, sendAwareness } = useRealtime({ organizationId, autoConnect });

  const [threads, setThreads] = useState<CommentThread[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);

  // Load threads from server
  const loadThreads = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/v1/documents/${documentId}/comments`, {
        headers: { 'Authorization': `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error('Failed to load comments');
      const data = await response.json();
      setThreads(data.threads || []);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to load comments');
    } finally {
      setLoading(false);
    }
  }, [documentId, accessToken]);

  // Initialize WebSocket connection for real-time updates
  const connect = useCallback(() => {
    if (!accessToken) return;

    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8999"}/api/v1/realtime/ws/comments/${documentId}?token=${accessToken}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[Comments] Connected');
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        handleMessage(message);
      } catch (e) {
        console.error('[Comments] Failed to parse message:', e);
      }
    };

    ws.onclose = () => {
      // Attempt reconnection
      setTimeout(() => connect(), 3000);
    };

    ws.onerror = (error) => {
      console.error('[Comments] WebSocket error:', error);
    };
  }, [accessToken]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
  }, []);

  const handleMessage = useCallback((message: any) => {
    switch (message.type) {
      case 'thread_created':
        setThreads(prev => [message.payload.thread, ...prev]);
        break;
      case 'thread_updated':
        setThreads(prev => prev.map(t => t.id === message.payload.thread.id ? message.payload.thread : t));
        break;
      case 'thread_deleted':
        setThreads(prev => prev.filter(t => t.id !== message.payload.threadId));
        break;
      case 'thread_resolved':
      case 'thread_reopened':
        setThreads(prev => prev.map(t => 
          t.id === message.payload.threadId 
            ? { ...t, resolved: message.type === 'thread_resolved', updatedAt: Date.now() }
            : t
        ));
        break;
      case 'comment_created':
        setThreads(prev => prev.map(t => {
          if (t.id === message.payload.threadId) {
            return { ...t, comments: [...t.comments, message.payload.comment], updatedAt: Date.now() };
          }
          return t;
        }));
        break;
      case 'comment_updated':
        setThreads(prev => prev.map(t => {
          if (t.id === message.payload.threadId) {
            return {
              ...t,
              comments: t.comments.map(c => c.id === message.payload.comment.id ? message.payload.comment : c),
              updatedAt: Date.now(),
            };
          }
          return t;
        }));
        break;
      case 'comment_deleted':
        setThreads(prev => prev.map(t => {
          if (t.id === message.payload.threadId) {
            return { ...t, comments: t.comments.filter(c => c.id !== message.payload.commentId), updatedAt: Date.now() };
          }
          return t;
        }));
        break;
      case 'comment_reaction':
        setThreads(prev => prev.map(t => {
          if (t.id !== message.payload.threadId) return t;
          
          const updatedComments = t.comments.map(c => {
            if (c.id === message.payload.commentId) {
              const reactions = { ...c.reactions };
              const users = reactions[message.payload.emoji] || [];
              if (message.payload.added) {
                reactions[message.payload.emoji] = [...users, message.payload.userId];
              } else {
                reactions[message.payload.emoji] = users.filter((id: string) => id !== message.payload.userId);
              }
              return { ...c, reactions }
            }
            return c;
          });
          return Object.assign({}, t, { comments: updatedComments });
        }));
      case 'mention':
        // Handle mention notifications
        break;
    }
  }, []);

  // Connect on mount
  useEffect(() => {
    loadThreads();
    if (autoConnect) {
      connect();
    }
    return () => disconnect();
  }, [loadThreads, connect, disconnect, autoConnect]);

  // Thread operations
  const createThread = useCallback(async (anchor: CommentThread['anchor'], initialComment: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        anchor,
        content: initialComment,
      }),
    });

    if (!response.ok) throw new Error('Failed to create thread');
    const data = await response.json();
    
    const newThread: CommentThread = data.thread;
    setThreads(prev => [newThread, ...prev]);
    onCommentChange?.([newThread, ...threads]);
    
    return newThread;
  }, [documentId, accessToken, threads]);

  const deleteThread = useCallback(async (threadId: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    if (!response.ok) throw new Error('Failed to delete thread');
    setThreads(prev => prev.filter(t => t.id !== threadId));
  }, [documentId, accessToken, threads]);

  const resolveThread = useCallback(async (threadId: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/resolve`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    if (!response.ok) throw new Error('Failed to resolve thread');
    const data = await response.json();
    setThreads(prev => prev.map(t => t.id === threadId ? { ...t, resolved: true, updatedAt: Date.now() } : t));
  }, [documentId, accessToken]);

  const reopenThread = useCallback(async (threadId: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/reopen`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    if (!response.ok) throw new Error('Failed to reopen thread');
    setThreads(prev => prev.map(t => t.id === threadId ? { ...t, resolved: false, updatedAt: Date.now() } : t));
  }, [documentId, accessToken]);

  const assignThread = useCallback(async (threadId: string, userId: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
      body: JSON.stringify({ userId }),
    });
    if (!response.ok) throw new Error('Failed to assign thread');
    const data = await response.json();
    setThreads(prev => prev.map(t => t.id === threadId ? { ...t, assignedTo: userId, updatedAt: Date.now() } : t));
  }, [documentId, accessToken]);

  const addLabel = useCallback(async (threadId: string, label: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/labels`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
      body: JSON.stringify({ label }),
    });
    if (!response.ok) throw new Error('Failed to add label');
    const data = await response.json();
    setThreads(prev => prev.map(t => t.id === threadId ? { ...t, labels: data.labels, updatedAt: Date.now() } : t));
  }, [documentId, accessToken]);

  const removeLabel = useCallback(async (threadId: string, label: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/labels/${encodeURIComponent(label)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    if (!response.ok) throw new Error('Failed to remove label');
    const data = await response.json();
    setThreads(prev => prev.map(t => t.id === threadId ? { ...t, labels: data.labels, updatedAt: Date.now() } : t));
  }, [documentId, accessToken]);

  // Comment operations
  const addComment = useCallback(async (threadId: string, content: string, parentId?: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
      body: JSON.stringify({ content, parentId }),
    });
    if (!response.ok) throw new Error('Failed to add comment');
    const data = await response.json();
    
    setThreads(prev => prev.map(t => {
      if (t.id === threadId) {
        return { ...t, comments: [...t.comments, data.comment], updatedAt: Date.now() };
      }
      return t;
    }));
    
    return data.comment;
  }, [documentId, accessToken, threads]);

  const updateComment = useCallback(async (threadId: string, commentId: string, content: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/comments/${commentId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
      body: JSON.stringify({ content }),
    });
    if (!response.ok) throw new Error('Failed to update comment');
    const data = await response.json();
    setThreads(prev => prev.map(t => {
      if (t.id === threadId) {
        return { ...t, comments: t.comments.map(c => c.id === commentId ? data.comment : c), updatedAt: Date.now() };
      }
      return t;
    }));
  }, [documentId, accessToken]);

  const deleteComment = useCallback(async (threadId: string, commentId: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/comments/${commentId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    if (!response.ok) throw new Error('Failed to delete comment');
    setThreads(prev => prev.map(t => {
      if (t.id === threadId) {
        return { ...t, comments: t.comments.filter(c => c.id !== commentId), updatedAt: Date.now() };
      }
      return t;
    }));
  }, [documentId, accessToken]);

  const reactToComment = useCallback(async (threadId: string, commentId: string, emoji: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/comments/${commentId}/reactions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
      body: JSON.stringify({ emoji }),
    });
    if (!response.ok) throw new Error('Failed to add reaction');
    const data = await response.json();
    setThreads(prev => prev.map(t => {
      if (t.id === threadId) {
        return {
          ...t,
          comments: t.comments.map(c => c.id === commentId ? { ...c, reactions: data.reactions } : c),
        };
      }
      return t;
    }));
  }, [documentId, accessToken]);

  const removeReaction = useCallback(async (threadId: string, commentId: string, emoji: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/comments/${commentId}/reactions/${encodeURIComponent(emoji)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    if (!response.ok) throw new Error('Failed to remove reaction');
    const data = await response.json();
    setThreads(prev => prev.map(t => {
      if (t.id === threadId) {
        return { ...t, comments: t.comments.map(c => c.id === commentId ? { ...c, reactions: data.reactions } : c) };
      }
      return t;
    }));
  }, [documentId, accessToken]);

  const mentionUser = useCallback(async (threadId: string, commentId: string, userId: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/comments/${commentId}/mentions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
      body: JSON.stringify({ userId }),
    });
    if (!response.ok) throw new Error('Failed to mention user');
  }, [documentId, accessToken]);

  // Real-time subscription
  const subscribe = useCallback(() => {
    // Already connected via WebSocket
  }, []);

  const unsubscribe = useCallback(() => {
    disconnect();
  }, [disconnect]);

  return {
    threads,
    loading,
    error,
    createThread,
    deleteThread,
    resolveThread,
    reopenThread: useCallback(async (threadId: string) => {
      const response = await fetch(`/api/v1/documents/${documentId}/comments/threads/${threadId}/reopen`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error('Failed to reopen thread');
      setThreads(prev => prev.map(t => t.id === threadId ? { ...t, resolved: false, updatedAt: Date.now() } : t));
    }, [documentId, accessToken]),
    assignThread,
    addLabel,
    removeLabel,
    addComment,
    updateComment,
    deleteComment,
    reactToComment,
    removeReaction,
    mentionUser,
    subscribe,
    unsubscribe,
  };
}

// Hook for managing annotations on documents (highlights, drawings, etc.)
export function useAnnotations(documentId: string) {
  const [annotations, setAnnotations] = useState<Array<{
    id: string;
    type: 'highlight' | 'underline' | 'strikethrough' | 'drawing' | 'shape' | 'text';
    anchor: {
      position: number;
      length: number;
      page?: number;
      x?: number;
      y?: number;
      width?: number;
      height?: number;
    };
    color: string;
    authorId: string;
    authorName: string;
    createdAt: number;
    updatedAt: number;
  }>([]);

  const [loading, setLoading] = useState(false);

  const loadAnnotations = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/v1/documents/${documentId}/annotations`);
      if (!response.ok) throw new Error('Failed to load annotations');
      const data = await response.json();
      setAnnotations(data.annotations || []);
    } catch (error) {
      console.error('Failed to load annotations:', error);
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    loadAnnotations();
  }, [loadAnnotations]);

  const createAnnotation = useCallback(async (annotation: Omit<typeof annotations[0], 'id' | 'createdAt' | 'updatedAt'>) => {
    const response = await fetch(`/api/v1/documents/${documentId}/annotations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(annotation),
    });
    if (!response.ok) throw new Error('Failed to create annotation');
    const data = await response.json();
    setAnnotations(prev => [...prev, data.annotation]);
    return data.annotation;
  }, [documentId]);

  const updateAnnotation = useCallback(async (id: string, updates: Partial<typeof annotations[0]>) => {
    const response = await fetch(`/api/v1/documents/${documentId}/annotations/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!response.ok) throw new Error('Failed to update annotation');
    const data = await response.json();
    setAnnotations(prev => prev.map(a => a.id === id ? data.annotation : a));
  }, [documentId]);

  const deleteAnnotation = useCallback(async (id: string) => {
    const response = await fetch(`/api/v1/documents/${documentId}/annotations/${id}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete annotation');
    setAnnotations(prev => prev.filter(a => a.id !== id));
  }, [documentId]);

  return {
    annotations,
    loading,
    createAnnotation,
    updateAnnotation,
    deleteAnnotation,
    refresh: loadAnnotations,
  };
}

// Hook for real-time presence in comments/annotations
export function useCommentPresence(documentId: string) {
  const { presences, isConnected } = useRealtime({ organizationId: '', autoConnect: false });

  const commentPresences = useMemo(() => 
    presences.filter(p => p.documentId === documentId),
    [presences, documentId]
  );

  return {
    presences: commentPresences,
    isConnected,
  };
}

// Hook for real-time typing indicators
export function useTypingIndicator(documentId: string, threadId?: string) {
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
  const typingTimeoutRef = useRef<Map<string, NodeJS.Timeout>>(new Map());

  const { sendAwareness } = useRealtime({ organizationId: '', autoConnect: false });

  const startTyping = useCallback(() => {
    // Send typing indicator via awareness
    if (threadId) {
      // Send typing indicator for specific thread
    } else {
      // Send typing indicator for document
    }
  }, [threadId]);

  const stopTyping = useCallback(() => {
    // Stop typing indicator
  }, []);

  // Auto-stop typing after timeout
  const setTyping = useCallback((userId: string, isTyping: boolean) => {
    if (isTyping) {
      setTypingUsers(function(prev) { return new Set([...prev, userId]); });
      // Auto-stop after 3 seconds
      const timeout = setTimeout(function() {
        setTypingUsers(function(prev) {
          const next = new Set(prev);
          next.delete(userId);
          return next;
        });
        typingTimeoutRef.current.delete(userId);
      }, 3000);
      typingTimeoutRef.current.set(userId, timeout);
    } else {
      setTypingUsers(function(prev) {
        const next = new Set(prev);
        next.delete(userId);
        return next;
      });
      const timeout = typingTimeoutRef.current.get(userId);
      if (timeout) {
        clearTimeout(timeout);
        typingTimeoutRef.current.delete(userId);
      }
    }
  }, [setTypingUsers, typingTimeoutRef]);

  return {
    typingUsers: Array.from(typingUsers),
    isTyping: typingUsers.size > 0,
    startTyping: () => setTyping(true),
    stopTyping: () => setTyping(false),
    setTyping,
  };
}