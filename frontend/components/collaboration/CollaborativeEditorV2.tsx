"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { Editor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { User, Wifi, WifiOff, AlertCircle, MessageSquare, Share2, MoreHorizontal } from "lucide-react";
import { classNames } from "@/lib/utils";
import { useCRDTDocument, CRDTOperation } from "@/hooks/useCRDT";
import { useRealtime } from "@/hooks/useRealtime";

// Remote cursor component for showing other users' cursor positions
interface RemoteCursorProps {
  user: {
    id: string;
    name: string;
    color: string;
    cursor?: { x: number; y: number };
    selection?: { anchor: number; head: number };
  };
  editorRef: React.RefObject<Editor | null>;
}

function RemoteCursor({ user, editorRef }: RemoteCursorProps) {
  if (!editorRef.current || !user.cursor) return null;

  const { x, y } = user.cursor;
  const { anchor, head } = user.selection || { anchor: x, head: y };
  
  // Get the editor view to calculate cursor position
  const view = editorRef.current.view;
  if (!view) return null;

  try {
    const startPos = Math.min(anchor, head);
    const endPos = Math.max(anchor, head);
    
    const startCoords = view.coordsAtPos(startPos);
    const endCoords = view.coordsAtPos(endPos);
    
    if (!startCoords || !endCoords) return null;

    const isSelection = startPos !== endPos;
    
    return (
      <div
        className="pointer-events-none"
        style={{
          position: "absolute",
          left: startCoords.left,
          top: startCoords.top - 20,
        }}
      >
        {/* Cursor caret */}
        <div
          className="remote-cursor-caret"
          style={{
            width: 2,
            height: 20,
            backgroundColor: user.color,
            position: "absolute",
            animation: "blink 1s infinite",
          }}
        />
        {/* User label */}
        <div
          className="remote-cursor-label"
          style={{
            position: "absolute",
            top: -20,
            left: 0,
            backgroundColor: user.color,
            color: "white",
            padding: "2px 6px",
            borderRadius: 4,
            fontSize: 10,
            fontWeight: 500,
            whiteSpace: "nowrap",
            transform: "translateX(-50%)",
          }}
        >
          {user.name}
        </div>
        {/* Selection highlight */}
        {isSelection && (
          <div
            className="remote-selection"
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              width: endCoords.left - startCoords.left,
              height: endCoords.bottom - startCoords.top,
              backgroundColor: `${user.color}40`,
              pointerEvents: "none",
            }}
          />
        )}
      </div>
    );
  } catch (e) {
    return null;
  }
}

interface CollaborativeEditorV2Props {
  documentId: string;
  organizationId: string;
  userId: string;
  userName: string;
  userColor?: string;
  userAvatar?: string | null;
  onContentChange?: (content: string) => void;
  placeholder?: string;
  readOnly?: boolean;
  className?: string;
}

export function CollaborativeEditorV2({
  documentId,
  organizationId,
  userId,
  userName,
  userColor,
  userAvatar,
  onContentChange,
  placeholder = "Start collaborating...",
  readOnly = false,
  className,
}: CollaborativeEditorV2Props) {
  const [isConnected, setIsConnected] = useState(false);
  const [connectedUsers, setConnectedUsers] = useState<Array<{
    id: string;
    name: string;
    color: string;
    cursor?: { x: number; y: number };
    selection?: { anchor: number; head: number };
  }>>([]);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const editorRef = useRef<Editor | null>(null);
  const editorContentRef = useRef<HTMLDivElement>(null);
  const cursorOverlayRef = useRef<HTMLDivElement>(null);

  // Use our CRDT hook for real-time collaboration
  const crdt = useCRDTDocument({
    documentId,
    crdtType: "ytext",
    autoConnect: true,
    onContentChange: (content) => {
      if (typeof content === "string" && onContentChange) {
        onContentChange(content);
      }
    },
    onPresenceChange: (clients) => {
      const users = Array.from(clients.entries()).map(([clientId, data]) => ({
        id: clientId,
        name: data.userName || "Unknown",
        color: data.userColor || generateColor(clientId),
        cursor: data.cursor,
        selection: data.selection,
      }));
      setConnectedUsers(users);
    },
    onConnectionChange: (connected) => {
      setIsConnected(connected);
    },
  });

  // Sync editor content with CRDT
  useEffect(() => {
    if (editorRef.current && crdt.content) {
      const currentText = editorRef.current.getText();
      if (currentText !== crdt.content) {
        editorRef.current.commands.setContent(crdt.content);
      }
    }
  }, [crdt.content]);

  // Use realtime for cursor/selection sync
  const realtime = useRealtime({
    organizationId,
    autoConnect: true,
    onMessage: (message) => {
      if (message.type === "cursor:update") {
        // Handle remote cursor updates
        const { user_id, cursor, selection } = message.payload;
        setConnectedUsers(prev => prev.map(u => 
          u.id === user_id ? { ...u, cursor, selection } : u
        ));
      }
    },
    onConnect: () => {
      realtime.joinRoom(documentId, "document");
    },
  });

  // Handle editor updates - send to CRDT
  const handleEditorUpdate = useCallback(({ editor }: { editor: Editor }) => {
    if (onContentChange) {
      onContentChange(editor.getText());
    }
  }, [onContentChange]);

  // Initialize Tiptap editor
  useEffect(() => {
    const editor = new Editor({
      element: editorContentRef.current,
      extensions: [
        StarterKit,
      ],
      content: crdt.content as string || "",
      editable: !readOnly,
      onUpdate: handleEditorUpdate,
    });

    editorRef.current = editor;

    return () => {
      editor.destroy();
      editorRef.current = null;
    };
  }, [readOnly, handleEditorUpdate, crdt.content]);

  // Handle cursor/selection updates from editor
  const handleSelectionUpdate = useCallback(() => {
    if (!editorRef.current || !realtime.isConnected) return;

    const { state } = editorRef.current;
    const { selection } = state;
    
    if (!selection.empty) {
      const { from, to } = selection;
      realtime.updateCursor(documentId, { x: from, y: to });
      // realtime.updateSelection({ start: from, end: to });
    }
  }, [realtime, documentId]);

  // Attach selection listener
  useEffect(() => {
    if (!editorRef.current) return;

    const view = editorRef.current.view;
    if (view) {
      const handleSelection = () => handleSelectionUpdate();
      view.dom.addEventListener("selectionchange", handleSelection);
      return () => view.dom.removeEventListener("selectionchange", handleSelection);
    }
  }, [handleSelectionUpdate]);

  // Helper to generate consistent color from userId
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

  const initials = useMemo(() => {
    return userName
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  }, [userName]);

  const avatarBgColor = useMemo(() => {
    if (userColor) return userColor;
    return generateColor(userId);
  }, [userColor, userId]);

  if (!editorRef.current) {
    return (
      <div
        className={classNames(
          "flex-1 flex flex-col border border-line rounded-xl bg-canvas",
          className,
        )}
      >
        <div className="flex items-center justify-center h-64 text-faint">
          Loading collaborative editor...
        </div>
      </div>
    );
  }

  return (
    <div
      className={classNames(
        "flex-1 flex flex-col border border-line rounded-xl bg-canvas overflow-hidden",
        className,
      )}
    >
      {/* Connection Status Bar */}
      <div
        className={classNames(
          "flex items-center justify-between px-4 py-2 border-b border-line bg-canvas/50",
          isConnected ? "bg-emerald-50" : "bg-red-50",
        )}
      >
        <div className="flex items-center gap-2">
          <span
            className={classNames(
              "flex items-center gap-1.5 text-xs font-medium",
              isConnected ? "text-emerald-700" : "text-red-700",
            )}
          >
            {isConnected ? (
              <>
                <svg
                  className="h-3 w-3"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
                  />
                </svg>
                Connected
              </>
            ) : (
              <>
                <svg
                  className="h-3 w-3"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
                  />
                </svg>
                Disconnected
              </>
            )}
          </span>
          {connectionError && (
            <span className="text-xs text-red-600">{connectionError}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex -space-x-2" title={`${connectedUsers.length} collaborators`}>
            {connectedUsers.slice(0, 5).map((user, index) => (
              <div
                key={user.id}
                className="relative z-[auto] w-7 h-7 rounded-full border-2 border-canvas flex items-center justify-center text-xs font-medium text-white overflow-hidden"
                style={{ backgroundColor: user.color }}
              >
                {user.name.charAt(0).toUpperCase()}
              </div>
            ))}
            {connectedUsers.length > 5 && (
              <div className="relative z-[auto] w-7 h-7 rounded-full border-2 border-canvas flex items-center justify-center text-xs font-medium text-muted bg-muted">
                +{connectedUsers.length - 5}
              </div>
            )}
          </div>
          {connectedUsers.length > 0 && (
            <span className="text-xs text-muted">
              {connectedUsers.length} {connectedUsers.length === 1 ? "other" : "others"} editing
            </span>
          )}
        </div>
      </div>

      {/* Editor Toolbar */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-line bg-canvas/50">
        <div className="flex items-center gap-1">
          <button
            onClick={() =>
              editorRef.current
                ?.chain()
                .focus()
                .toggleHeading({ level: 1 })
                .run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Heading 1"
          >
            <span className="text-xs font-bold">H1</span>
          </button>
          <button
            onClick={() =>
              editorRef.current
                ?.chain()
                .focus()
                .toggleHeading({ level: 2 })
                .run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Heading 2"
          >
            <span className="text-xs font-bold">H2</span>
          </button>
          <button
            onClick={() =>
              editorRef.current
                ?.chain()
                .focus()
                .toggleHeading({ level: 3 })
                .run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Heading 3"
          >
            <span className="text-xs font-bold">H3</span>
          </button>
        </div>
        <div className="w-px h-6 bg-line mx-2" />
        <div className="flex items-center gap-1">
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleBold().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Bold (⌘B)"
          >
            <span className="text-xs font-bold">B</span>
          </button>
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleItalic().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Italic (⌘I)"
          >
            <span className="text-xs font-italic">I</span>
          </button>
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleStrike().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Strikethrough"
          >
            <span className="text-xs line-through">S</span>
          </button>
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleCode().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Inline Code"
          >
            <span className="text-xs font-mono">`</span>
          </button>
        </div>
        <div className="w-px h-6 bg-line mx-2" />
        <div className="flex items-center gap-1">
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleBulletList().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Bullet List"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleOrderedList().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Numbered List"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleTaskList().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Task List"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          </button>
        </div>
        <div className="w-px h-6 bg-line mx-2" />
        <div className="flex items-center gap-1">
          <button
            onClick={() =>
              editorRef.current?.chain().focus().setBlockquote().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Quote"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 14v3m4-3v3m-8-6H4m8 0h4" />
            </svg>
          </button>
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleCodeBlock().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Code Block"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
          </button>
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          {/* User Avatar */}
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium text-white" style={{ backgroundColor: avatarBgColor }}>
            {userAvatar ? (
              <img src={userAvatar} alt={userName} className="w-full h-full rounded-full" />
            ) : (
              initials
            )}
          </div>
        </div>
      </div>

      {/* Editor Content */}
      <div className="flex-1 overflow-auto p-4 relative">
        <EditorContent
          ref={editorContentRef}
          editor={editorRef.current}
          className="prose prose-sm max-w-none focus:outline-none min-h-[400px]"
          placeholder={placeholder}
        />
        {/* Remote cursors and selections */}
        <div ref={cursorOverlayRef} className="absolute inset-0 pointer-events-none">
          {connectedUsers.map((user) => (
            user.cursor && (
              <RemoteCursor
                key={user.id}
                user={user}
                editorRef={editorRef}
              />
            )
          ))}
        </div>
      </div>
    </div>
  );
}