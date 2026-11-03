"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { 
  FileText, 
  Users, 
  MessageSquare, 
  Video, 
  Share2, 
  Settings,
  ChevronLeft,
  ChevronRight,
  X,
  MoreHorizontal,
  Search,
  Sparkles,
  Plus,
  ArrowDownLeft,
  ArrowUpRight
} from "lucide-react";
import { classNames } from "@/lib/utils";
import { CollaborativeEditorV2 } from "@/components/collaboration/CollaborativeEditorV2";
import { CommentThreadView } from "@/components/collaboration/CommentThread";
import { ScreenSharePreview, ScreenShareButton } from "@/components/collaboration/ScreenShare";
import { useAuth } from "@/hooks/useAuth";
import { useComments } from "@/hooks/useComments";
import { useScreenShare } from "@/hooks/useScreenShare";
import { useRealtime, PresenceData } from "@/hooks/useRealtime";

export default function CollaborationDocumentPage() {
  const params = useParams();
  const router = useRouter();
  const documentId = params.documentId as string;
  const { user, accessToken, organization } = useAuth();
  const organizationId = organization?.id || "";

  const [activeTab, setActiveTab] = useState<"editor" | "comments" | "calls" | "activity">("editor");
  const [showSidebar, setShowSidebar] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(320);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [documentTitle, setDocumentTitle] = useState("Untitled Document");

  // Real-time connected users from presence
  const [connectedUsers, setConnectedUsers] = useState<Array<{
    id: string;
    name: string;
    color: string;
    avatar?: string;
    cursor?: { x: number; y: number };
    selection?: { start: number; end: number };
  }>>([]);

  const { threads, loading: commentsLoading, createThread, resolveThread, reopenThread } = useComments({
    documentId,
    organizationId: organization?.id || "",
    autoConnect: true,
  });

  const { isSharing, stream, startScreenShare, stopScreenShare } = useScreenShare();

  // Real-time connection for presence and collaboration
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
          selection: p.selection,
        }));
        setConnectedUsers(users);
      }
    },
    onPresenceChange: (presences) => {
      const users = presences.map((p: any) => ({
        id: p.user_id,
        name: p.user_name,
        color: p.user_color,
        cursor: p.cursor,
        selection: p.selection,
      }));
      setConnectedUsers(users);
    },
    onConnect: () => {
      console.log("[Collab] Connected to real-time");
      // Join the document room
      realtime.joinRoom(documentId, "document");
    },
    onDisconnect: () => {
      console.log("[Collab] Disconnected from real-time");
    },
  });

  const sidebarResizerRef = useRef<HTMLDivElement>(null);
  const startXRef = useRef(0);

  // Initialize document
  useEffect(() => {
    // In production, fetch document from API
    setDocumentTitle("Project Alpha - Strategic Plan");
  }, [documentId]);

  // Join document room on connect
  useEffect(() => {
    if (realtime.isConnected) {
      realtime.joinRoom(documentId, "document");
    }
    return () => {
      realtime.leaveRoom(documentId);
    };
  }, [realtime.isConnected, documentId, realtime]);

  // Handle sidebar resize
  const handleMouseDown = (e: React.MouseEvent) => {
    startXRef.current = e.clientX;
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    e.preventDefault();
  };

  const handleMouseMove = (e: MouseEvent) => {
    const delta = startXRef.current - e.clientX;
    const newWidth = Math.max(280, Math.min(500, sidebarWidth + delta));
    setSidebarWidth(newWidth);
  };

  const handleMouseUp = () => {
    document.removeEventListener("mousemove", handleMouseMove);
    document.removeEventListener("mouseup", handleMouseUp);
  };

  // Handle new comment thread creation from editor
  const handleCreateThreadFromEditor = useCallback(async (anchor: { position: number; length: number }) => {
    // In production, open a modal to add initial comment
    console.log("Create thread at anchor:", anchor);
  }, []);

  // Handle comment thread selection
  const handleThreadSelect = useCallback((threadId: string) => {
    setActiveTab("comments");
    // The CommentThreadView will handle selection
  }, []);

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
            {/* AI Assistant */}
            <button className="p-2 rounded-lg hover:bg-muted transition-colors flex items-center gap-2 text-sm font-medium" title="Ask AI">
              <Sparkles className="h-4 w-4 text-brand" />
              <span className="hidden sm:inline">Ask AI</span>
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

        {/* Tab Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Editor Tab */}
          {activeTab === "editor" && (
            <div className="flex-1 flex flex-col">
              <CollaborativeEditorV2
                documentId={documentId}
                organizationId={organization?.id || ""}
                userId={user?.id || ""}
                userName={user?.full_name || user?.email || "Anonymous"}
                userColor={connectedUsers[0]?.color}
                onContentChange={(content) => {
                  // Save content
                }}
                placeholder="Start collaborating in real-time..."
              />
            </div>
          )}

          {/* Comments Tab */}
          {activeTab === "comments" && (
            <div className="flex-1 flex flex-col">
              <CommentThreadView
                documentId={documentId}
                organizationId={organization?.id || ""}
                onThreadSelect={handleThreadSelect}
              />
            </div>
          )}

          {/* Calls Tab */}
          {activeTab === "calls" && (
            <div className="flex-1 flex flex-col">
              <div className="flex h-full">
                {/* Video Call List/Grid */}
                <div className="flex-1 p-6">
                  <div className="flex items-center justify-between mb-6">
                    <h2 className="text-xl font-semibold">Video Calls</h2>
                    <button className="px-4 py-2 bg-brand text-white rounded-lg font-medium hover:bg-brand-strong flex items-center gap-2">
                      <Video className="h-4 w-4" />
                      Start Call
                    </button>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {/* Recent Calls */}
                    <div className="p-4 border border-line rounded-xl bg-canvas">
                      <h3 className="font-medium mb-3">Recent Calls</h3>
                      <div className="space-y-2 text-sm text-muted">
                        <p>No recent calls</p>
                      </div>
                    </div>
                    {/* Scheduled Calls */}
                    <div className="p-4 border border-line rounded-xl bg-canvas">
                      <h3 className="font-medium mb-3">Scheduled</h3>
                      <div className="space-y-2 text-sm text-muted">
                        <p>No scheduled calls</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Sidebar for Calls */}
                {showSidebar && (
                  <div className={classNames(
                    "flex flex-col border-l border-line bg-canvas transition-all duration-300",
                    "w-[320px] flex-shrink-0"
                  )} style={{ width: sidebarWidth }}>
                    <div className="p-4 border-b border-line">
                      <h3 className="font-medium">Call Controls</h3>
                    </div>
                    <div className="flex-1 p-4 space-y-4">
                      <ScreenShareButton
                        onStart={async () => { await startScreenShare(); }}
                        onStop={async () => { stopScreenShare(); }}
                        isSharing={isSharing}
                      />
                      {isSharing && stream && (
                        <ScreenSharePreview
                          stream={stream}
                          isSharing={isSharing}
                          onStop={stopScreenShare}
                        />
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Activity Tab */}
          {activeTab === "activity" && (
            <div className="flex-1 flex flex-col">
              <div className="flex-1 p-6">
                <h2 className="text-xl font-semibold mb-6">Document Activity</h2>
                <div className="space-y-4 max-h-[calc(100vh-200px)] overflow-y-auto">
                  {/* Activity feed would go here */}
                  <div className="text-center text-muted py-12">
                    <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>No activity yet</p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right Sidebar - Comments & Activity */}
      {showSidebar && (
        <div className={classNames(
          "flex flex-col border-l border-line bg-canvas transition-all duration-300 overflow-hidden flex-shrink-0",
          "w-[320px]"
        )} style={{ width: sidebarWidth }}>
          {/* Sidebar Resizer */}
          <div
            ref={sidebarResizerRef}
            onMouseDown={handleMouseDown}
            className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-brand/20 transition-colors"
            aria-label="Resize sidebar"
          >
            <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1">
              <div className="w-px h-6 bg-line rounded" />
              <div className="w-px h-6 bg-line rounded" />
            </div>
          </div>

          {/* Sidebar Tabs */}
          <div className="flex border-b border-line bg-canvas/50">
            {[
              { id: "editor", label: "Editor", icon: FileText, count: 0 },
              { id: "comments", label: "Comments", icon: MessageSquare, count: threads.filter(t => !t.resolved).length },
              { id: "calls", label: "Calls", icon: Video, count: 0 },
              { id: "activity", label: "Activity", icon: Users, count: 0 },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={classNames(
                  "flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-sm font-medium transition-colors relative",
                  activeTab === tab.id
                    ? "text-brand border-b-2 border-brand"
                    : "text-muted hover:text-ink hover:bg-muted"
                )}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
                {tab.count > 0 && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-brand/10 text-brand">
                    {tab.count}
                  </span>
                )}
              </button>
            ))}

            <button
              onClick={() => setShowSidebar(false)}
              className="p-2 rounded-r-lg hover:bg-muted transition-colors lg:hidden"
              aria-label="Close sidebar"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>

          {/* Sidebar Content */}
          <div className="flex-1 overflow-hidden">
            {/* Comments Sidebar */}
            {activeTab === "comments" && (
              <div className="flex flex-col h-full">
                <CommentThreadView
                  documentId={documentId}
                  organizationId={organization?.id || ""}
                  onThreadSelect={handleThreadSelect}
                  readOnly={false}
                />
              </div>
            )}

            {/* Connected Users Sidebar */}
            {activeTab === "editor" && (
              <div className="flex flex-col h-full p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-medium">Collaborators</h3>
                  <span className="text-xs text-muted">{connectedUsers.length} online</span>
                </div>
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

            {/* Calls Sidebar */}
            {activeTab === "calls" && (
              <div className="flex flex-col h-full p-4">
                <h3 className="font-medium mb-4">Call Controls</h3>
                <ScreenShareButton
                  onStart={async () => { await startScreenShare(); }}
                  onStop={async () => { stopScreenShare(); }}
                  isSharing={isSharing}
                />
                {isSharing && stream && (
                  <ScreenSharePreview
                    stream={stream}
                    isSharing={isSharing}
                    onStop={stopScreenShare}
                    className="mt-4"
                  />
                )}
              </div>
            )}

            {/* Activity Sidebar */}
            {activeTab === "activity" && (
              <div className="flex flex-col h-full p-4">
                <h3 className="font-medium mb-4">Recent Activity</h3>
                <div className="flex-1 overflow-y-auto space-y-3">
                  <p className="text-center text-muted py-8">No recent activity</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
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