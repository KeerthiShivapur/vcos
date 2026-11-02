"use client";

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useComments } from '@/hooks/useComments';
import { 
  MessageSquare, 
  CheckCircle, 
  Circle, 
  Flag, 
  User, 
  MoreHorizontal, 
  Edit, 
  Trash2, 
  Reply, 
  Heart, 
  ThumbsUp,
  Smile,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  AtSign,
  Pin,
  Flag as FlagIcon,
  Edit2,
  Trash,
  Archive,
  ArrowLeft,
  ArrowRight,
  Send,
  Paperclip,
  Smile as SmileIcon,
  Search,
  Filter,
  MoreVertical,
  EllipsisVertical
} from "lucide-react";
import { classNames } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";

interface CommentThreadProps {
  documentId: string;
  organizationId: string;
  threadId?: string;
  className?: string;
  onThreadSelect?: (threadId: string) => void;
  readOnly?: boolean;
}

interface Comment {
  id: string;
  threadId: string;
  parentId?: string;
  documentId: string;
  anchor: {
    position?: number;
    length?: number;
    cell?: string;
    x?: number;
    y?: number;
  };
  authorId: string;
  authorName: string;
  authorColor: string;
  content: string;
  createdAt: number;
  updatedAt: number;
  resolved: boolean;
  reactions: Record<string, string[]>;
  mentions: string[];
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
  anchor: {
    position?: number;
    length?: number;
    cell?: string;
    x?: number;
    y?: number;
  };
  comments: any[];
  resolved: boolean;
  createdAt: number;
  updatedAt: number;
  createdBy: string;
  assignedTo?: string;
  labels: string[];
}

export function CommentThreadView({
  documentId,
  organizationId,
  threadId,
  className,
  onThreadSelect,
  readOnly = false,
}: CommentThreadProps) {
  const { user, accessToken } = useAuth();
  const { 
    threads, 
    loading, 
    error,
    createThread, 
    resolveThread, 
    reopenThread 
  } = useComments({
    documentId,
    organizationId,
    autoConnect: true,
  });

  const [selectedThread, setSelectedThread] = useState<any>(threadId
    ? threads.find(t => t.id === threadId) || null
    : null);
  const [filter, setFilter] = useState<'all' | 'open' | 'resolved'>('all');
  const [sortBy, setSortBy] = useState<'newest' | 'oldest' | 'most-replies'>('newest');
  const [showNewThread, setShowNewThread] = useState(false);
  const [newThreadAnchor, setNewThreadAnchor] = useState<{ position: number; length: number } | null>(null);
  const [editingComment, setEditingComment] = useState<{ 
    threadId: string; 
    commentId: string; 
    content: string 
  } | null>(null);
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyContent, setReplyContent] = useState('');
  const [showEmojiPicker, setShowEmojiPicker] = useState<{ 
    threadId: string; 
    commentId: string 
  } | null>(null);
  const [showMentions, setShowMentions] = useState<{ 
    threadId: string; 
    commentId: string 
  } | null>(null);

  const filteredThreads = useMemo(() => {
    let filtered = threads;
    if (filter === 'open') filtered = filtered.filter(t => !t.resolved);
    else if (filter === 'resolved') filtered = filtered.filter(t => t.resolved);
    
    if (sortBy === 'newest') {
      filtered.sort((a, b) => b.updatedAt - a.updatedAt);
    } else if (sortBy === 'oldest') {
      filtered.sort((a, b) => a.updatedAt - b.updatedAt);
    } else if (sortBy === 'most-replies') {
      filtered.sort((a, b) => b.comments.length - a.comments.length);
    }
    return filtered;
  }, [threads, filter, sortBy]);

  // Load thread on mount or threadId change
  useEffect(() => {
    if (threadId) {
      const thread = threads.find(t => t.id === threadId);
      if (thread) setSelectedThread(thread);
    }
  }, [threadId, threads]);

  const handleCreateThread = async (anchor: { position: number; length: number }) => {
    setNewThreadAnchor(anchor);
    setShowNewThread(true);
  };

  const handleResolveThread = async (threadId: string) => {
    // await resolveThread(threadId);
  };

  const handleReopenThread = async (threadId: string) => {
    // await reopenThread(threadId);
  };

  const handleDeleteThread = async (threadId: string) => {
    if (!confirm('Are you sure you want to delete this thread?')) return;
    try {
      // await deleteThread(threadId);
      setSelectedThread(null);
    } catch (error) {
      console.error('Failed to delete thread:', error);
    }
  };

  const handleReply = (commentId: string) => {
    // setReplyingTo(commentId);
  };

  const handleEditComment = (threadId: string, commentId: string, content: string) => {
    // setEditingComment({ threadId, commentId, content });
  };

  const handleUpdateComment = async (content: string) => {
    // if (editingComment) {
    //   await updateComment(editingComment.threadId, editingComment.commentId, content);
    //   setEditingComment(null);
    // }
  };

  const handleDeleteComment = async (threadId: string, commentId: string) => {
    if (!confirm('Are you sure you want to delete this comment?')) return;
    try {
      // await deleteComment(threadId, commentId);
    } catch (error) {
      console.error('Failed to delete comment:', error);
    }
  };

  const handleReact = async (commentId: string, emoji: string) => {
    // await reactToComment(commentId, emoji);
  };

  const handleMention = async (commentId: string, userId: string) => {
    // await mentionUser(commentId, userId);
  };

  const handleResolve = async (threadId: string) => {
    // await resolveThread(threadId);
  };

  const handleReopen = async (threadId: string) => {
    // await reopenThread(threadId);
  };

  const handleDelete = async (threadId: string) => {
    if (!confirm('Are you sure you want to delete this thread?')) return;
    try {
      // await deleteThread(threadId);
    } catch (error) {
      console.error('Failed to delete thread:', error);
    }
  };

  const handleAddComment = async (anchor: { position: number; length: number }, content: string) => {
    // await addComment({ threadId: selectedThread?.id, content, anchor });
    setNewThreadAnchor(null);
    setShowNewThread(false);
  };

  // Render thread list
  const renderThreadList = () => {
    if (threads.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-faint">
          <MessageSquare className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-brand" />
          <span className="text-sm">No threads yet</span>
          <button
            onClick={() => setShowNewThread(true)}
            className="btn-primary px-4 py-2"
          >
            <MessageSquare className="h-4 w-4 mr-2" />
            Create First Thread
          </button>
        </div>
      );
    }

    return (
      <div className="divide-y divide-line">
        {filteredThreads.map((thread) => (
          <div 
            key={thread.id}
            className="p-4 hover:bg-muted/50 cursor-pointer transition-colors"
          >
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium text-white" style={{ backgroundColor: '#3B82F6' }}>
                {thread.createdBy?.charAt(0).toUpperCase() || 'T'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium truncate">Thread {thread.id.slice(0, 8)}</h3>
                  <span className={'px-2 py-0.5 text-xs rounded-full ' + (thread.resolved ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700')}>
                    {thread.resolved ? 'Resolved' : 'Open'}
                  </span>
                </div>
                <p className="text-sm text-muted mt-1 truncate">
                  {thread.comments?.[0]?.content || 'No comments yet'}
                </p>
                <div className="flex items-center gap-4 mt-2 text-xs text-muted">
                  <span>{thread.comments?.length || 0} comments</span>
                  <span>{new Date(thread.updatedAt).toLocaleDateString()}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-faint">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-brand" />
          <span className="text-sm">Loading comments...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <div className="p-4 text-center text-red-500">
          <div className="flex items-center justify-center gap-2">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>Failed to load comments: {error}</span>
          </div>
          <button 
            onClick={() => window.location.reload()}
            className="mt-2 px-4 py-2 bg-brand text-white rounded-lg hover:bg-brand-strong"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={'flex flex-col h-full bg-canvas border border-line rounded-xl ' + (className || '')}>
      {/* Header */}
      <div className="flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-line bg-canvas/50">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold">Comments</h2>
            <span className="px-2 py-0.5 text-xs font-medium bg-muted rounded-full">
              {threads.filter(t => !t.resolved).length} open
            </span>
            <span className="px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 rounded-full">
              {threads.filter(t => t.resolved).length} resolved
            </span>
          </div>
          
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 border border-line rounded-lg bg-canvas p-1">
              <button
                onClick={() => setFilter('all')}
                className={'px-3 py-1.5 text-xs rounded-md transition-colors ' + (filter === 'all' ? 'bg-brand text-white' : 'text-muted hover:bg-muted')}
              >
                All
              </button>
              <button
                onClick={() => setFilter('open')}
                className={'px-3 py-1.5 text-xs rounded-md transition-colors ' + (filter === 'open' ? 'bg-brand text-white' : 'text-muted hover:bg-muted')}
              >
                Open
              </button>
              <button
                onClick={() => setFilter('resolved')}
                className={'px-3 py-1.5 text-xs rounded-md transition-colors ' + (filter === 'resolved' ? 'bg-brand text-white' : 'text-muted hover:bg-muted')}
              >
                Resolved
              </button>
            </div>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="input py-1.5 text-sm"
            >
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="most-replies">Most Replies</option>
            </select>
            <button
              onClick={() => setShowNewThread(true)}
              className="btn-primary px-4 py-2"
            >
              <MessageSquare className="h-4 w-4 mr-2" />
              New Thread
            </button>
          </div>
        </div>

        {/* Threads List */}
        <div className="flex-1 overflow-y-auto">
          {renderThreadList()}
        </div>
      </div>
    </div>
  );
}

function generateColor(id: string): string {
  const colors = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFBE0B", "#FB5607",
    "#8338EC", "#3A86FF", "#06D6A0", "#FF9F1C", "#FF6F61",
  ];
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  return colors[hash % colors.length];
}