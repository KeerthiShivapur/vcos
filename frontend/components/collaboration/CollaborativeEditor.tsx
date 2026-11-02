"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { Editor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Collaboration from "@tiptap/extension-collaboration";
import CollaborationCursor from "@tiptap/extension-collaboration-cursor";
import { PresenceData } from "@/hooks/useRealtime";
import { PresenceIndicator } from "@/components/ui/PresenceIndicator";
import {
  User,
  Wifi,
  WifiOff,
  AlertCircle,
  AtSign,
  MessageSquare,
  Users,
  Share2,
  MoreHorizontal,
} from "lucide-react";
import { classNames } from "@/lib/utils";

interface CollaborativeEditorProps {
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

interface AwarenessState {
  user: {
    id: string;
    name: string;
    color: string;
  };
  cursor?: { x: number; y: number };
  selection?: { anchor: number; head: number };
}

export function CollaborativeEditor({
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
}: CollaborativeEditorProps) {
  const [isConnected, setIsConnected] = useState(false);
  const [connectedUsers, setConnectedUsers] = useState<PresenceData[]>([]);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const ydocRef = useRef<Y.Doc | null>(null);
  const providerRef = useRef<any>(null);
  const awarenessRef = useRef<any>(null);
  const editorRef = useRef<any>(null);
  const editorContentRef = useRef<HTMLDivElement>(null);

  // Initialize Yjs document and WebSocket provider
  useEffect(() => {
    // Create Yjs document
    const ydoc = new Y.Doc();
    ydocRef.current = ydoc;

    // Create WebSocket provider for collaboration
    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8999"}/api/v1/yjs/ws/${documentId}`;
    const provider = new WebsocketProvider(wsUrl, documentId, ydoc, {
      connect: true,
    });
    providerRef.current = provider;

    // Set up awareness for cursor/selection sharing
    const awareness = provider.awareness;
    awarenessRef.current = awareness;

    // Set local user info
    awareness.setLocalStateField("user", {
      id: userId,
      name: userName,
      color: userColor || generateColor(userId),
    });

    // Track connected users
    const updateConnectedUsers = () => {
      const states: any[] = [];
      awareness.getStates().forEach((state: any, clientId: number) => {
        if (state?.user && clientId !== awareness.clientID) {
          states.push({
            user: state.user,
            cursor: state.cursor,
            selection: state.selection,
          });
        }
      });
      setConnectedUsers(states);
    };

    // Connection status handlers
    provider.on("status", (event: { status: string }) => {
      setIsConnected(event.status === "connected");
      setConnectionError(
        event.status === "connected"
          ? null
          : "Disconnected from collaboration server",
      );
    });

    // Awareness changes
    awareness.on("change", () => {
      updateConnectedUsers();
    });

    // Sync document content
    const ytext = ydoc.getText("content");
    ytext.observe(() => {
      if (onContentChange && editorRef.current) {
        onContentChange(editorRef.current.getText());
      }
    });

    // Initialize Tiptap editor with collaboration extensions
    const editor = new Editor({
      element: editorContentRef.current,
      extensions: [
        StarterKit,
        Collaboration.configure({
          document: ydoc,
        }),
        CollaborationCursor.configure({
          provider,
          user: {
            name: userName,
            color: userColor || generateColor(userId),
          },
        }),
      ],
      content: "",
      editable: !readOnly,
      onUpdate: ({ editor }) => {
        if (onContentChange) {
          onContentChange(editor.getText());
        }
      },
    });

    editorRef.current = editor;

    // Cleanup function
    return () => {
      provider.disconnect();
      provider.destroy();
      awareness.destroy();
      ydoc.destroy();
      editor.destroy();
      editorRef.current = null;
      providerRef.current = null;
      awarenessRef.current = null;
      ydocRef.current = null;
    };
  }, [
    documentId,
    userId,
    userName,
    userColor,
    organizationId,
    readOnly,
    onContentChange,
  ]);

  // Helper to generate consistent color from userId
  function generateColor(id: string): string {
    const colors = [
      "#FF6B6B",
      "#4ECDC4",
      "#45B7D1",
      "#FFBE0B",
      "#FB5607",
      "#8338EC",
      "#3A86FF",
      "#06D6A0",
      "#FF9F1C",
      "#FF6F61",
    ];
    let hash = 0;
    for (let i = 0; i < id.length; i++) {
      hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
    }
    return colors[hash % colors.length];
  }

  // Get initials for avatar fallback
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
          <div
            className="flex -space-x-2"
            title={`${connectedUsers.length} collaborators`}
          >
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
              {connectedUsers.length}{" "}
              {connectedUsers.length === 1 ? "other" : "others"} editing
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
            <svg
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleOrderedList().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Numbered List"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleTaskList().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Task List"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
              />
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
            <svg
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 14v3m4-3v3m-8-6H4m8 0h4"
              />
            </svg>
          </button>
          <button
            onClick={() =>
              editorRef.current?.chain().focus().toggleCodeBlock().run()
            }
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Code Block"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Editor Content */}
      <div className="flex-1 overflow-auto p-4">
        <EditorContent
          ref={editorContentRef}
          editor={editorRef.current}
          className="prose prose-sm max-w-none focus:outline-none min-h-[400px]"
          placeholder={placeholder}
        />
      </div>
    </div>
  );
}
