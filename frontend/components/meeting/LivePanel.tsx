"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Hand, MessageSquare, MonitorUp, Radio, Send, Video, Volume2 } from "lucide-react";

import { API_URL, addMeetingCaption, getMeetingWhiteboard, listMeetingCaptions, listMeetingChat, listMeetingRecordings, sendMeetingChat, startMeetingRecording, stopMeetingRecording, tokenStore, updateMeetingWhiteboard } from "@/lib/api";
import type { MeetingCaption, MeetingChatMessage, MeetingParticipant, MeetingRecording, MeetingWhiteboard } from "@/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { Input } from "@/components/ui/Input";
import { toastError, toastSuccess } from "@/components/ui/Toaster";
import { formatDateTime } from "@/lib/utils";

interface LivePeer {
  employee_id: string;
  name: string;
  role?: string;
  online?: boolean;
}

interface LivePanelProps {
  meetingId: string;
  myEmployeeId: string | null;
  isHost: boolean;
  recordingState?: { is_recording: boolean; started_at: string | null };
}

interface BoardShape {
  id: string;
  kind: "rect" | "ellipse" | "line";
  x: number;
  y: number;
  w: number;
  h: number;
}

function wsUrl(meetingId: string, token: string): string {
  const base = API_URL.replace(/^http/, "ws");
  const apiPath = base.indexOf("/api/") >= 0 ? base.slice(0, base.indexOf("/api/")) : base;
  return `${apiPath}/ws/meetings/${meetingId}?token=${encodeURIComponent(token)}`;
}

let shapeSeq = 0;

export function LivePanel({ meetingId, myEmployeeId, isHost, recordingState }: LivePanelProps) {
  const [connected, setConnected] = useState(false);
  const [peers, setPeers] = useState<LivePeer[]>([]);
  const [chat, setChat] = useState<MeetingChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [captionInput, setCaptionInput] = useState("");
  const [captions, setCaptions] = useState<MeetingCaption[]>([]);
  const [board, setBoard] = useState<MeetingWhiteboard | null>(null);
  const [draftShapes, setDraftShapes] = useState<BoardShape[]>([]);
  const [tool, setTool] = useState<"rect" | "ellipse" | "line">("rect");
  const [drawing, setDrawing] = useState<{ kind: BoardShape["kind"]; x0: number; y0: number; x1: number; y1: number } | null>(null);
  const [reactions, setReactions] = useState<{ id: number; emoji: string; name: string }[]>([]);
  const [raisedHand, setRaisedHand] = useState(false);
  const [sending, setSending] = useState(false);
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [sharing, setSharing] = useState(false);
  const [recordings, setRecordings] = useState<MeetingRecording[]>([]);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const chatRef = useRef<HTMLDivElement | null>(null);
  const reactionSeq = useRef(0);

  const sendWs = useCallback((type: string, data?: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, data: data ?? {} }));
    }
  }, []);

  // ---------------------------------------------------------------- chat

  const appendChat = useCallback((message: MeetingChatMessage) => {
    setChat((rows) => {
      if (rows.some((r) => r.id === message.id)) return rows;
      return [...rows, message];
    });
  }, []);

  async function handleSendChat(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = chatInput.trim();
    if (!content) return;
    setSending(true);
    try {
      const message = await sendMeetingChat(meetingId, content);
      appendChat(message);
      sendWs("chat", { content });
      setChatInput("");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to send message");
    } finally {
      setSending(false);
    }
  }

  // ---------------------------------------------------------------- whiteboard

  async function refreshBoard() {
    try {
      setBoard(await getMeetingWhiteboard(meetingId));
      setDraftShapes([]);
    } catch {
      /* board fetch is best-effort */
    }
  }

  const savedShapes: BoardShape[] = (board?.content?.shapes as BoardShape[]) ?? [];

  function pointerDown(event: React.PointerEvent<SVGSVGElement>) {
    if (!board) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 800;
    const y = ((event.clientY - rect.top) / rect.height) * 500;
    setDrawing({ kind: tool, x0: x, y0: y, x1: x, y1: y });
  }

  function pointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (!drawing) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(800, ((event.clientX - rect.left) / rect.width) * 800));
    const y = Math.max(0, Math.min(500, ((event.clientY - rect.top) / rect.height) * 500));
    setDrawing({ ...drawing, x1: x, y1: y });
  }

  async function pointerUp() {
    if (!drawing || !board) {
      setDrawing(null);
      return;
    }
    const shape: BoardShape = {
      id: `s${Date.now()}_${shapeSeq++}`,
      kind: drawing.kind,
      x: Math.min(drawing.x0, drawing.x1),
      y: Math.min(drawing.y0, drawing.y1),
      w: Math.abs(drawing.x1 - drawing.x0),
      h: Math.abs(drawing.y1 - drawing.y0),
    };
    setDrawing(null);
    if (shape.w < 2 && shape.h < 2) return;
    const next = [...savedShapes, shape];
    try {
      const updated = await updateMeetingWhiteboard(meetingId, { shapes: next }, board.version);
      setBoard(updated);
      setDraftShapes([]);
      sendWs("whiteboard.delta", { version: updated.version, ops: [{ type: "shape", shape }] });
    } catch {
      toastError("Board changed elsewhere — refreshing");
      await refreshBoard();
    }
  }

  async function clearBoard() {
    if (!board) return;
    try {
      const updated = await updateMeetingWhiteboard(meetingId, { shapes: [] }, board.version);
      setBoard(updated);
      sendWs("whiteboard.delta", { version: updated.version, ops: [{ type: "clear" }] });
    } catch {
      await refreshBoard();
    }
  }

  // ---------------------------------------------------------------- websocket

  useEffect(() => {
    let disposed = false;
    let heartbeat: ReturnType<typeof setInterval> | null = null;
    let ping: ReturnType<typeof setInterval> | null = null;

    async function connect() {
      const token = tokenStore.getAccess();
      if (!token) return;
      const ws = new WebSocket(wsUrl(meetingId, token));
      wsRef.current = ws;
      ws.onopen = () => {
        if (disposed) return;
        setConnected(true);
        heartbeat = setInterval(() => sendWs("heartbeat"), 25000);
        ping = setInterval(() => {
          void loadCaptions();
        }, 6000);
        void refreshBoard();
      };
      ws.onmessage = (event) => {
        let envelope: { type: string; data: Record<string, unknown> };
        try {
          envelope = JSON.parse(String(event.data));
        } catch {
          return;
        }
        const data = envelope.data ?? {};
        switch (envelope.type) {
          case "welcome":
            setPeers((data.peers as LivePeer[]) ?? []);
            break;
          case "peer.online":
            setPeers((rows) => {
              const next = rows.filter((p) => p.employee_id !== data.employee_id);
              return [...next, { employee_id: String(data.employee_id), name: String(data.name ?? "Unknown"), role: String(data.role ?? "participant") }];
            });
            break;
          case "peer.offline":
            setPeers((rows) => rows.filter((p) => p.employee_id !== data.employee_id));
            break;
          case "chat.message":
            appendChat(data.message as MeetingChatMessage);
            break;
          case "whiteboard.delta":
            void refreshBoard();
            break;
          case "reaction":
            setReactions((rows) => [
              ...rows.slice(-6),
              { id: reactionSeq.current++, emoji: String(data.emoji ?? "👍"), name: String(data.employee_id ?? "") },
            ]);
            break;
          case "pong":
            break;
          case "error":
            toastError(String(data.message ?? "Live error"));
            break;
          default:
            break;
        }
      };
      ws.onclose = () => {
        if (disposed) return;
        setConnected(false);
        if (heartbeat) clearInterval(heartbeat);
        if (ping) clearInterval(ping);
        setTimeout(() => {
          if (!disposed) void connect();
        }, 3000);
      };
      ws.onerror = () => {
        ws.close();
      };
    }

    void connect();
    return () => {
      disposed = true;
      if (heartbeat) clearInterval(heartbeat);
      if (ping) clearInterval(ping);
      wsRef.current?.close();
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meetingId]);

  // ---------------------------------------------------------------- data load

  useEffect(() => {
    void listMeetingChat(meetingId).then(setChat).catch(() => undefined);
    void loadCaptions();
    void loadRecordings();
    const timer = setInterval(() => void loadCaptions(), 8000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meetingId]);

  async function loadCaptions() {
    try {
      const rows = await listMeetingCaptions(meetingId, undefined, "en");
      setCaptions((prev) => {
        const merged = [...rows];
        for (const row of prev) {
          if (!merged.some((r) => r.id === row.id)) merged.push(row);
        }
        return merged.sort((a, b) => (a.start_ms ?? 0) - (b.start_ms ?? 0));
      });
    } catch {
      /* best-effort */
    }
  }

  async function loadRecordings() {
    try {
      setRecordings(await listMeetingRecordings(meetingId));
    } catch {
      /* best-effort */
    }
  }

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [chat.length]);

  useEffect(() => {
    const timer = setTimeout(() => setReactions([]), 3500);
    return () => clearTimeout(timer);
  }, [reactions]);

  async function pushCaption() {
    const text = captionInput.trim();
    if (!text) return;
    try {
      await addMeetingCaption(meetingId, { text, language: "en" });
      setCaptionInput("");
      await loadCaptions();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to add caption");
    }
  }

  async function toggleRecording() {
    setBusy(true);
    try {
      if (!recording) {
        await startMeetingRecording(meetingId, { kind: "manual", captions_enabled: true });
        toastSuccess("Recording started");
        setRecording(true);
      } else {
        const active = recordings.find((r) => r.status === "recording");
        if (active) await stopMeetingRecording(meetingId, active.id);
        toastSuccess("Recording stopped");
        setRecording(false);
      }
      await loadRecordings();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Recording action failed");
    } finally {
      setBusy(false);
    }
  }

  function togglePresence(kind: "mic" | "cam") {
    const nextMic = kind === "mic" ? !micOn : micOn;
    const nextCam = kind === "cam" ? !camOn : camOn;
    if (kind === "mic") setMicOn(nextMic);
    else setCamOn(nextCam);
    sendWs("presence", { mic_enabled: nextMic, camera_enabled: nextCam });
  }

  function toggleHand() {
    const next = !raisedHand;
    setRaisedHand(next);
    sendWs("raise_hand", { raised: next });
  }

  function toggleShare() {
    const next = !sharing;
    setSharing(next);
    sendWs("screen_share", { sharing: next });
  }

  const activeRecording = recordings.find((r) => r.status === "recording");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={connected ? "success" : "danger"}>{connected ? "connected" : "offline"}</Badge>
        <Badge tone="neutral">{peers.length + 1} in session</Badge>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button size="sm" variant={micOn ? "primary" : "secondary"} onClick={() => togglePresence("mic")}>
            <Volume2 className="h-3.5 w-3.5" /> {micOn ? "Mic on" : "Mic off"}
          </Button>
          <Button size="sm" variant={camOn ? "primary" : "secondary"} onClick={() => togglePresence("cam")}>
            <Video className="h-3.5 w-3.5" /> {camOn ? "Cam on" : "Cam off"}
          </Button>
          <Button size="sm" variant={sharing ? "primary" : "secondary"} onClick={toggleShare}>
            <MonitorUp className="h-3.5 w-3.5" /> {sharing ? "Sharing" : "Share"}
          </Button>
          <Button size="sm" variant={raisedHand ? "secondary" : "ghost"} onClick={toggleHand}>
            <Hand className="h-3.5 w-3.5" /> {raisedHand ? "Hand raised" : "Raise hand"}
          </Button>
          {(isHost || recordingState?.is_recording) && (
            <Button size="sm" variant={activeRecording || recording ? "danger" : "secondary"} onClick={toggleRecording} loading={busy}>
              <Radio className="h-3.5 w-3.5" /> {activeRecording || recording ? "Stop recording" : "Record"}
            </Button>
          )}
        </div>
      </div>

      {reactions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {reactions.map((reaction) => (
            <span key={reaction.id} className="animate-bounce rounded-full bg-brand-soft px-2.5 py-1 text-[13px]">
              {reaction.name ? `${reaction.name.split(" ")[0]}: ` : ""}
              {reaction.emoji}
            </span>
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {/* ------------------------------------------------ chat */}
        <div className="card flex flex-col p-4">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-brand" />
            <p className="text-[13px] font-semibold text-ink">In-meeting chat</p>
            <span className="ml-auto rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-brand">{chat.length}</span>
          </div>
          <div ref={chatRef} className="mt-3 max-h-72 flex-1 space-y-2.5 overflow-y-auto pr-1">
            {chat.length === 0 && <p className="text-[12px] text-faint">No messages yet — say hello.</p>}
            {chat.map((message) => (
              <div key={message.id} className="rounded-lg border border-line p-2.5">
                <div className="flex items-center gap-1.5">
                  <span className="text-[12px] font-semibold text-ink">{message.sender_name ?? "You"}</span>
                  <span className="text-[10px] text-faint">{message.created_at ? formatDateTime(message.created_at) : ""}</span>
                </div>
                <p className="mt-0.5 text-[13px] leading-relaxed text-muted">{message.content}</p>
              </div>
            ))}
          </div>
          <form onSubmit={handleSendChat} className="mt-3 flex gap-2">
            <Input
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Message everyone…"
              className="flex-1"
            />
            <Button type="submit" size="sm" loading={sending}>
              <Send className="h-3.5 w-3.5" />
            </Button>
          </form>
        </div>

        {/* ------------------------------------------------ whiteboard */}
        <div className="card p-4 lg:col-span-1">
          <div className="flex items-center gap-2">
            <p className="text-[13px] font-semibold text-ink">Whiteboard</p>
            <div className="ml-auto flex items-center gap-1">
              {(["rect", "ellipse", "line"] as const).map((kind) => (
                <button
                  key={kind}
                  onClick={() => setTool(kind)}
                  className={`rounded-md px-2 py-1 text-[11px] font-medium ${tool === kind ? "bg-brand-soft text-brand" : "text-faint hover:bg-canvas"}`}
                >
                  {kind}
                </button>
              ))}
              <button onClick={clearBoard} className="ml-1 rounded-md px-2 py-1 text-[11px] font-medium text-faint hover:bg-danger/10 hover:text-danger">
                Clear
              </button>
            </div>
          </div>
          <svg
            viewBox="0 0 800 500"
            className="mt-3 h-64 w-full touch-none rounded-lg border border-line bg-canvas"
            onPointerDown={pointerDown}
            onPointerMove={pointerMove}
            onPointerUp={pointerUp}
            onPointerLeave={pointerUp}
          >
            {savedShapes.map((shape) => <ShapeElement key={shape.id} shape={shape} />)}
            {draftShapes.map((shape) => <ShapeElement key={shape.id} shape={shape} />)}
            {drawing && <ShapeElement shape={{ id: "draft", kind: drawing.kind, x: Math.min(drawing.x0, drawing.x1), y: Math.min(drawing.y0, drawing.y1), w: Math.abs(drawing.x1 - drawing.x0), h: Math.abs(drawing.y1 - drawing.y0) }} />}
          </svg>
          <p className="mt-2 text-[11px] text-faint">v{board?.version ?? 1} · changes sync to everyone in the session</p>
        </div>

        {/* ------------------------------------------------ people + captions */}
        <div className="space-y-4">
          <div className="card p-4">
            <p className="text-[13px] font-semibold text-ink">Participants</p>
            <ul className="mt-2 space-y-1.5">
              {peers.map((peer) => (
                <li key={peer.employee_id} className="flex items-center gap-2">
                  <Avatar name={peer.name} size="sm" />
                  <span className="truncate text-[13px] text-ink">{peer.name}</span>
                  {peer.role === "host" && <Badge tone="brand">host</Badge>}
                </li>
              ))}
              {myEmployeeId && peers.every((p) => p.employee_id !== myEmployeeId) && (
                <li className="flex items-center gap-2 text-[12px] text-faint">you are connected</li>
              )}
            </ul>
          </div>

          <div className="card p-4">
            <p className="text-[13px] font-semibold text-ink">Live captions</p>
            <div className="mt-2 max-h-44 space-y-1.5 overflow-y-auto">
              {captions.length === 0 && <p className="text-[12px] text-faint">No captions yet.</p>}
              {captions.slice(-8).map((caption) => (
                <p key={caption.id} className="text-[12px] leading-relaxed text-muted">
                  {caption.speaker_name && <span className="font-semibold text-ink">{caption.speaker_name}: </span>}
                  {caption.translated_text && caption.translation_language ? caption.translated_text : caption.text}
                </p>
              ))}
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void pushCaption();
              }}
              className="mt-2 flex gap-2"
            >
              <Input
                value={captionInput}
                onChange={(event) => setCaptionInput(event.target.value)}
                placeholder="Add a caption line…"
                className="flex-1"
              />
              <Button type="submit" size="sm">
                <Volume2 className="h-3.5 w-3.5" />
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

function ShapeElement({ shape }: { shape: BoardShape }) {
  const common = { stroke: "#6366f1", strokeWidth: 2, fill: "none" };
  if (shape.kind === "rect") return <rect {...common} x={shape.x} y={shape.y} width={shape.w} height={shape.h} />;
  if (shape.kind === "ellipse") return <ellipse {...common} cx={shape.x + shape.w / 2} cy={shape.y + shape.h / 2} rx={shape.w / 2} ry={shape.h / 2} />;
  return <line {...common} x1={shape.x} y1={shape.y} x2={shape.x + shape.w} y2={shape.y + shape.h} />;
}
