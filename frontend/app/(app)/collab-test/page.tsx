"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FileText, Users, Share2, Settings, ArrowDownLeft, ArrowUpRight, X, MessageSquare, Send, ChevronDown } from "lucide-react";
import { classNames } from "@/lib/utils";
import { CollaborativeEditorV2 } from "@/components/collaboration/CollaborativeEditorV2";
import { useAuth } from "@/hooks/useAuth";
import { useRealtime } from "@/hooks/useRealtime";

interface Comment {
  id: string;
  authorId: string;
  authorName: string;
  authorColor: string;
  content: string;
  createdAt: number;
  resolved: boolean;
}

export default function CollabTestPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const documentId = searchParams.get("doc") || "test-doc-1";
  const { user, accessToken } = useAuth();
  const organizationId = user?.organization_id || "";

  const [documentTitle, setDocumentTitle] = useState("Test Document");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [connectedUsers, setConnectedUsers] = useState<Array<{
    id: string;
    name: string;
    color: string;
    cursor?: { x: number; y: number };
    selection?: { start: number; end: number };
  }>>([]);
  const [activeSidebar, setActiveSidebar] = useState<"users" | "comments">("users");
  const [comments, setComments] = useState<Comment[]>([]);
  const [newComment, setNewComment] = useState("");

  // Use our Socket.IO realtime hook
  const realtime = useRealtime({
    organizationId,
    autoConnect: true,
    onRoomState: (state) => {
      if (state.participants) {
        const users = state.participants.map((p: any) => ({
          id: p.user_id,
          name: p.user_name,
          color: p.user_color,
          cursor: p.cursor,
        }));
        setConnectedUsers(users);
      }
    },
    onMessage: (message) => {
      console.log("[CollabTest] Message:", message);
      if (message.type === "comment:new") {
        setComments(prev => [...prev, message.payload]);
      } else if (message.type === "comment:resolve") {
        setComments(prev => prev.map(c => c.id === message.payload.id ? { ...c, resolved: true } : c));
      }
    },
    onConnect: () => {
      console.log("[CollabTest] Connected to real-time");
      // Join the document room
      realtime.joinRoom(documentId, "document");
    },
    onDisconnect: () => {
      console.log("[CollabTest] Disconnected from real-time");
    },
  });

  // Join room on connect
  useEffect(() => {
    if (realtime.isConnected) {
      realtime.joinRoom(documentId, "document");
    }
  }, [realtime.isConnected, documentId, realtime]);

  // Handle cursor updates from other users
  useEffect(() => {
    // The realtime hook handles cursor updates via onRoomState
  }, [realtime.presences]);

  const handleCreateDocument = useCallback(async () => {
    // In production, create document via API
    router.push(`/collab-test?doc=new-doc-${Date.now()}`);
  }, [router]);

  const handleSendComment = useCallback(() => {
    if (!newComment.trim() || !user) return;
    
    const comment: Comment = {
      id: crypto.randomUUID(),
      authorId: user.id,
      authorName: user.full_name || user.email || "Anonymous",
      authorColor: connectedUsers[0]?.color || "#3B82F6",
      content: newComment,
      createdAt: Date.now(),
      resolved: false,
    };
    
    setComments(prev => [...prev, comment]);
    realtime.sendMessage(documentId, JSON.stringify({ type: "comment", ...comment }), "comment");
    setNewComment("");
  }, [newComment, user, connectedUsers, realtime, documentId]);

  const handleResolveComment = useCallback((commentId: string) => {
    setComments(prev => prev.map(c => c.id === commentId ? { ...c, resolved: true } : c));
    realtime.sendMessage(documentId, JSON.stringify({ type: "comment:resolve", id: commentId }), "comment");
  }, [realtime, documentId]);

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Main Editor Area */}
      <div className={classNames(
        "flex-1 flex flex-col overflow-hidden transition-all duration-300",
        isFullscreen && "fixed inset-0 z-50"
      )}>
        {/* Top Toolbar */}
        <div className={classNames(
          "flex items-center justify-between px-4 py-3 border-b border-line bg-canvas/80 backdrop-blur-sm",
          isFullscreen ? "fixed top-0 left-0 right-0 z-40" : ""
        )}>
          <div className="flex items-center gap-3">
            {/* Fullscreen Toggle */}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2 rounded-lg hover:bg-muted transition-colors lg:hidden"
              aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
            >
              {isFullscreen ? <ArrowDownLeft className="h-5 w-5" /> : <ArrowUpRight className="h-5 w-5" />}
            </button>

            {/* Document Title */}
            <div className="flex-1 min-w-0">
              <input
                type="text"
                value={documentTitle}
                onChange={(e) => setDocumentTitle(e.target.value)}
                className="w-full bg-transparent border-none text-lg font-semibold text-ink placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2 rounded"
                placeholder="Untitled Document"
              />
            </div>

            {/* Connected Users */}
            <div className="flex items-center gap-1">
              {connectedUsers.slice(0, 5).map((u, i) => (
                <div
                  key={u.id}
                  className={classNames(
                    "w-8 h-8 rounded-full border-2 border-canvas flex items-center justify-center text-xs font-medium text-white transition-transform",
                    i > 0 && "-ml-2"
                  )}
                  style={{ backgroundColor: u.color, zIndex: 5 - i }}
                  title={u.name}
                >
                  {u.name.charAt(0).toUpperCase()}
                </div>
              ))}
              {connectedUsers.length > 5 && (
                <div className="w-8 h-8 rounded-full border-2 border-canvas flex items-center justify-center text-xs font-medium text-muted bg-muted -ml-2">
                  +{connectedUsers.length - 5}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* New Document */}
            <button
              onClick={handleCreateDocument}
              className="px-3 py-1.5 rounded-lg hover:bg-muted transition-colors text-sm font-medium flex items-center gap-2"
            >
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">New Doc</span>
            </button>

            {/* Share */}
            <button className="p-2 rounded-lg hover:bg-muted transition-colors" title="Share">
              <Share2 className="h-5 w-5" />
            </button>

            {/* Settings */}
            <button className="p-2 rounded-lg hover:bg-muted transition-colors" title="Settings">
              <Settings className="h-5 w-5" />
            </button>

            {/* Exit Fullscreen */}
            {isFullscreen && (
              <button
                onClick={() => setIsFullscreen(false)}
                className="p-2 rounded-lg hover:bg-muted transition-colors lg:hidden"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>
        </div>

        {/* Connection Status */}
        <div className={classNames(
          "px-4 py-1 border-b border-line text-xs",
          realtime.isConnected ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
        )}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1.5">
                {realtime.isConnected ? (
                  <>
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 005.656-5.656l-1.1 1.1" />
                    </svg>
                    Socket.IO Connected
                  </>
                ) : (
                  <>
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 005.656-5.656l-1.1 1.1" />
                    </svg>
                    Disconnected
                  </>
                )}
              </span>
              {realtime.connectionError && (
                <span className="ml-2 text-red-600">{realtime.connectionError}</span>
              )}
            </div>
            <div className="flex items-center gap-2 text-muted">
              <span>Doc: {documentId}</span>
              <span>Org: {organizationId.slice(0, 8)}...</span>
              <span>User: {user?.id?.slice(0, 8)}...</span>
            </div>
          </div>
        </div>

        {/* Editor */}
        <div className="flex-1 flex">
          <CollaborativeEditorV2
            documentId={documentId}
            organizationId={organizationId}
            userId={user?.id || ""}
            userName={user?.full_name || user?.email || "Anonymous"}
            userColor={connectedUsers[0]?.color}
            onContentChange={(content) => {
              console.log("[CollabTest] Content changed:", content.slice(0, 100));
            }}
            placeholder="Start collaborating in real-time..."
          />
        </div>
      </div>

      {/* Right Sidebar - Users & Comments */}
      <div className={classNames(
        "flex flex-col border-l border-line bg-canvas transition-all duration-300 overflow-hidden flex-shrink-0 w-[320px]"
      )}>
        {/* Sidebar Tabs */}
        <div className="flex border-b border-line bg-canvas/50">
          <button
            onClick={() => setActiveSidebar("users")}
            className={classNames(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-sm font-medium transition-colors relative",
              activeSidebar === "users"
                ? "text-brand border-b-2 border-brand"
                : "text-muted hover:text-ink hover:bg-muted"
            )}
          >
            <Users className="h-4 w-4" />
            Collaborators ({connectedUsers.length})
          </button>
          <button
            onClick={() => setActiveSidebar("comments")}
            className={classNames(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-sm font-medium transition-colors relative",
              activeSidebar === "comments"
                ? "text-brand border-b-2 border-brand"
                : "text-muted hover:text-ink hover:bg-muted"
            )}
          >
            <MessageSquare className="h-4 w-4" />
            Comments ({comments.filter(c => !c.resolved).length})
            {comments.filter(c => !c.resolved).length > 0 && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-brand/10 text-brand">
                {comments.filter(c => !c.resolved).length}
              </span>
            )}
          </button>
        </div>

        {/* Sidebar Content */}
        <div className="flex-1 overflow-hidden">
          {/* Users Sidebar */}
          {activeSidebar === "users" && (
            <div className="flex flex-col h-full p-4">
              <div className="flex-1 overflow-y-auto space-y-2">
                {connectedUsers.length === 0 ? (
                  <p className="text-center text-muted py-8">No collaborators yet</p>
                ) : (
                  connectedUsers.map((u) => (
                    <div key={u.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted transition-colors">
                      <div className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium text-white" style={{ backgroundColor: u.color }}>
                        {u.name.charAt(0).toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{u.name}</p>
                        <p className="text-xs text-muted flex items-center gap-1">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          Active
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Comments Sidebar */}
          {activeSidebar === "comments" && (
            <div className="flex flex-col h-full">
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {comments.length === 0 ? (
                  <p className="text-center text-muted py-8">No comments yet</p>
                ) : (
                  comments.map((comment) => (
                    <div
                      key={comment.id}
                      className={`p-3 rounded-lg border transition-colors ${
                        comment.resolved 
                          ? "bg-muted/30 border-line opacity-60" 
                          : "bg-surface border-brand/20"
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium text-white flex-shrink-0" style={{ backgroundColor: comment.authorColor }}>
                          {comment.authorName.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-medium">{comment.authorName}</p>
                              <span className="text-xs text-muted">
                                {new Date(comment.createdAt).toLocaleTimeString()}
                              </span>
                            </div>
                            {!comment.resolved && (
                              <button
                                onClick={() => handleResolveComment(comment.id)}
                                className="p-1 rounded hover:bg-muted transition-colors text-muted"
                                title="Resolve"
                              >
                                <ChevronDown className="h-4 w-4" />
                              </button>
                            )}
                          </div>
                          <p className="mt-1 text-sm text-ink">{comment.content}</p>
                          {comment.resolved && (
                            <p className="mt-2 text-xs text-muted italic">✓ Resolved</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
              
              {/* Add Comment Form */}
              <div className="p-4 border-t border-line">
                <div className="flex gap-2">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium text-white flex-shrink-0" style={{ backgroundColor: connectedUsers[0]?.color || "#3B82F6" }}>
                    {user?.full_name?.charAt(0).toUpperCase() || user?.email?.charAt(0).toUpperCase() || "U"}
                  </div>
                  <div className="flex-1 flex gap-2">
                    <input
                      type="text"
                      value={newComment}
                      onChange={(e) => setNewComment(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSendComment())}
                      placeholder="Add a comment..."
                      className="flex-1 input py-2 text-sm"
                    />
                    <button
                      onClick={handleSendComment}
                      disabled={!newComment.trim() || !realtime.isConnected}
                      className="btn-primary px-3 py-2"
                    >
                      <Send className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
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