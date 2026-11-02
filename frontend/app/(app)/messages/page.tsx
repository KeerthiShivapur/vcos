"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { Pencil, Pin, Search, Send, Smile, Trash2 } from "lucide-react";

import {
  archiveConversation,
  createConversation,
  deleteMessage,
  editMessage,
  getMyEmployee,
  listConversations,
  listEmployees,
  listMessages,
  listMyMentions,
  markConversationRead,
  markMessageRead,
  openDm,
  reactToMessage,
  sendMessage,
  toggleMessagePin,
} from "@/lib/api";
import { messagingChannel } from "@/lib/websocket";
import type { ChatMessage, Conversation, EmployeeSummary } from "@/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { timeAgo } from "@/lib/utils";

const POLL_INTERVAL_MS = 30_000;

export default function MessagesPage() {
  return (
    <Suspense fallback={null}>
      <MessagesContent />
    </Suspense>
  );
}

function MessagesContent() {
  const [myEmployeeId, setMyEmployeeId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mentions, setMentions] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newMessage, setNewMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [tab, setTab] = useState<"conversations" | "mentions">("conversations");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const lastMessageIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    lastMessageIds.current = new Set(messages.map((m) => m.id));
  }, [messages]);

  async function loadConversations() {
    try {
      const [list, people, mentionList, me] = await Promise.all([
        listConversations(),
        listEmployees({ page_size: 200 }),
        listMyMentions(20),
        getMyEmployee().catch(() => null),
      ]);
      setConversations(list);
      setEmployees(people);
      setMentions(mentionList);
      setMyEmployeeId(me?.id ?? null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load conversations",
      );
    }
  }

  async function openConversation(id: string) {
    setActiveId(id);
    setLoading(true);
    try {
      const [list, mentionList] = await Promise.all([
        listMessages(id),
        listMyMentions(20),
      ]);
      setMessages(list);
      setMentions(mentionList);
      markConversationRead(id).catch(() => undefined);
      list.forEach((m) => markMessageRead(m.id).catch(() => undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load messages");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadConversations().then(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const applyMessage = (data: Record<string, unknown>) => {
      const message = data.message as ChatMessage | undefined;
      const conversationId = String(data.conversation_id ?? "");
      if (!message || message.conversation_id !== conversationId) return;
      setMessages((rows) =>
        rows.some((r) => r.id === message.id) ? rows : [...rows, message],
      );
      if (activeId === conversationId) {
        markConversationRead(conversationId).catch(() => undefined);
        markMessageRead(message.id).catch(() => undefined);
      }
      setConversations((rows) =>
        rows.map((c) =>
          c.id === conversationId
            ? {
                ...c,
                message_count: c.message_count + 1,
                last_message_at: message.created_at,
                last_message_preview: message.content ?? "",
                unread_count: activeId === c.id ? 0 : c.unread_count + 1,
              }
            : c,
        ),
      );
      if (myEmployeeId && message.mentions.includes(myEmployeeId)) {
        listMyMentions(20)
          .then(setMentions)
          .catch(() => undefined);
      }
    };

    const updateMessage = (data: Record<string, unknown>) => {
      const message = data.message as ChatMessage | undefined;
      if (!message) return;
      setMessages((rows) =>
        rows.map((r) => (r.id === message.id ? message : r)),
      );
      setMentions((rows) =>
        rows.map((r) => (r.id === message.id ? message : r)),
      );
      setConversations((rows) =>
        rows.map((c) =>
          c.id === message.conversation_id
            ? {
                ...c,
                last_message_preview: message.deleted
                  ? "(deleted)"
                  : (message.content ?? ""),
              }
            : c,
        ),
      );
    };

    const removeMessage = (data: Record<string, unknown>) => {
      const messageId = String(data.message_id ?? "");
      if (!messageId) return;
      const tombstone = {
        deleted: true,
        content: null,
      } as Partial<ChatMessage>;
      setMessages((rows) =>
        rows.map((r) => (r.id === messageId ? { ...r, ...tombstone } : r)),
      );
      setMentions((rows) =>
        rows.map((r) => (r.id === messageId ? { ...r, ...tombstone } : r)),
      );
    };

    const applyReaction = (data: Record<string, unknown>) => {
      const messageId = String(data.message_id ?? "");
      if (!messageId) return;
      const emoji = String(data.emoji ?? "👍");
      const reacted = Boolean(data.reacted);
      setMessages((rows) =>
        rows.map((r) => {
          if (r.id !== messageId) return r;
          const reactions = [...r.reactions];
          const idx = reactions.findIndex((x) => x.emoji === emoji);
          if (reacted) {
            if (idx >= 0)
              reactions[idx] = { emoji, count: reactions[idx].count + 1 };
            else reactions.push({ emoji, count: 1 });
          } else if (idx >= 0) {
            if (reactions[idx].count <= 1) reactions.splice(idx, 1);
            else reactions[idx] = { emoji, count: reactions[idx].count - 1 };
          }
          return {
            ...r,
            reactions,
            reaction_count: Math.max(0, r.reaction_count + (reacted ? 1 : -1)),
          };
        }),
      );
    };

    const memberAdded = () => {
      loadConversations().catch(() => undefined);
    };

    const unsubscribes = [
      messagingChannel.subscribe("messaging.message.sent", applyMessage),
      messagingChannel.subscribe("messaging.message.updated", updateMessage),
      messagingChannel.subscribe("messaging.message.deleted", removeMessage),
      messagingChannel.subscribe("messaging.message.reaction", applyReaction),
      messagingChannel.subscribe("messaging.member.added", memberAdded),
    ];
    return () => unsubscribes.forEach((unsubscribe) => unsubscribe());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, myEmployeeId]);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, activeId]);

  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const list = await listConversations();
        setConversations(list);
        if (!activeId) return;
        const rows = await listMessages(activeId);
        const fresh = rows.filter((m) => !lastMessageIds.current.has(m.id));
        setMessages(rows);
        if (fresh.length > 0) {
          markConversationRead(activeId).catch(() => undefined);
          fresh.forEach((m) => markMessageRead(m.id).catch(() => undefined));
        }
      } catch {
        /* best-effort 30s fallback */
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(poll);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  async function startDm(employeeId: string) {
    try {
      const conversation = await openDm(employeeId);
      await loadConversations();
      await openConversation(conversation.id);
      setTab("conversations");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to open conversation",
      );
    }
  }

  async function startChannel() {
    try {
      const conversation = await createConversation({
        type: "channel",
        title: "General",
        channel_kind: "general",
        channel_key: "general",
      });
      await loadConversations();
      await openConversation(conversation.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create channel");
    }
  }

  async function submit() {
    if (!activeId || !newMessage.trim()) return;
    setSending(true);
    try {
      const sent = await sendMessage(activeId, { content: newMessage.trim() });
      setMessages((prev) => [...prev, sent]);
      setNewMessage("");
      await loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to send message");
    } finally {
      setSending(false);
    }
  }

  async function react(message: ChatMessage, emoji: string) {
    try {
      await reactToMessage(message.id, emoji);
      await openConversation(activeId!);
    } catch {
      /* ignore */
    }
  }

  async function pin(message: ChatMessage) {
    try {
      await toggleMessagePin(message.id);
      await openConversation(activeId!);
    } catch {
      /* ignore */
    }
  }

  function startEdit(message: ChatMessage) {
    setEditingId(message.id);
    setEditDraft(message.content ?? "");
  }

  async function saveEdit(id: string) {
    const content = editDraft.trim();
    if (!content) return;
    try {
      const updated = await editMessage(id, content);
      setMessages((rows) => rows.map((r) => (r.id === id ? updated : r)));
      setMentions((rows) => rows.map((r) => (r.id === id ? updated : r)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to edit message");
    } finally {
      setEditingId(null);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this message?")) return;
    try {
      await deleteMessage(id);
      const tombstone = {
        deleted: true,
        content: null,
      } as Partial<ChatMessage>;
      setMessages((rows) =>
        rows.map((r) => (r.id === id ? { ...r, ...tombstone } : r)),
      );
      setMentions((rows) =>
        rows.map((r) => (r.id === id ? { ...r, ...tombstone } : r)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete message");
    }
  }

  const active = conversations.find((c) => c.id === activeId) ?? null;

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col">
      <PageHeader
        title="Messages"
        description="Chat with your team."
        actions={
          <Button variant="secondary" size="sm" onClick={startChannel}>
            + General channel
          </Button>
        }
      />

      {error && <ErrorState title="Could not load messages" message={error} />}

      <div className="mt-4 grid min-h-0 flex-1 grid-cols-[280px_1fr] gap-4">
        <div className="flex min-h-0 flex-col rounded-lg border border-line bg-surface">
          <div className="flex border-b border-line">
            <button
              className={`flex-1 px-3 py-2.5 text-[13px] font-semibold ${tab === "conversations" ? "border-b-2 border-brand text-brand" : "text-faint"}`}
              onClick={() => setTab("conversations")}
            >
              Conversations
            </button>
            <button
              className={`flex-1 px-3 py-2.5 text-[13px] font-semibold ${tab === "mentions" ? "border-b-2 border-brand text-brand" : "text-faint"}`}
              onClick={() => setTab("mentions")}
            >
              Mentions
            </button>
          </div>

          {tab === "conversations" ? (
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  onClick={() => openConversation(conversation.id)}
                  className={`w-full rounded-md px-3 py-2.5 text-left transition hover:bg-surface-muted ${
                    conversation.id === activeId ? "bg-brand-soft" : ""
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-[13px] font-semibold text-ink">
                      {conversation.title ??
                        (conversation.type === "channel" ? "# " : "") +
                          "Direct message"}
                    </p>
                    {conversation.unread_count > 0 && (
                      <Badge tone="brand">{conversation.unread_count}</Badge>
                    )}
                  </div>
                  <p className="truncate text-[12px] text-faint">
                    {conversation.type} · {conversation.message_count} messages
                  </p>
                </button>
              ))}
              <div className="mt-2 border-t border-line pt-2">
                <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-faint">
                  Start a DM
                </p>
                {employees
                  .filter((e) => e.id !== myEmployeeId)
                  .slice(0, 20)
                  .map((employee) => (
                    <button
                      key={employee.id}
                      onClick={() => startDm(employee.id)}
                      className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left hover:bg-surface-muted"
                    >
                      <Avatar name={employee.full_name} size="xs" />
                      <span className="truncate text-[13px] text-muted">
                        {employee.full_name}
                      </span>
                    </button>
                  ))}
              </div>
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {mentions.length === 0 ? (
                <p className="p-3 text-[12px] text-faint">No mentions yet.</p>
              ) : (
                mentions.map((mention) => (
                  <button
                    key={mention.id}
                    onClick={() => openConversation(mention.conversation_id)}
                    className="w-full rounded-md px-3 py-2 text-left hover:bg-surface-muted"
                  >
                    <p className="truncate text-[13px] text-ink">
                      {mention.sender_name} mentioned you
                    </p>
                    <p className="truncate text-[12px] text-faint">
                      {mention.content}
                    </p>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        <div className="flex min-h-0 flex-col rounded-lg border border-line bg-surface">
          {active ? (
            <>
              <div className="flex items-center justify-between border-b border-line px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-ink">
                    {active.title ?? "Direct message"}
                  </p>
                  <p className="text-[12px] text-faint">
                    {active.type} · {active.member_count} members
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    archiveConversation(active.id).then(loadConversations)
                  }
                >
                  Archive
                </Button>
              </div>

              <div
                ref={listRef}
                className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4"
              >
                {loading ? (
                  <div className="flex justify-center py-12">
                    <Spinner label="Loading messages" />
                  </div>
                ) : messages.length === 0 ? (
                  <EmptyState
                    title="No messages yet"
                    description="Say hello to get things started."
                  />
                ) : (
                  messages.map((message) => (
                    <div
                      key={message.id}
                      className={`flex gap-2 ${message.sender_id === myEmployeeId ? "flex-row-reverse" : ""}`}
                    >
                      <div
                        className={`max-w-[70%] rounded-lg px-3 py-2 ${message.sender_id === myEmployeeId ? "bg-brand text-white" : "bg-surface-muted text-ink"}`}
                      >
                        {message.sender_id !== myEmployeeId && (
                          <p className="text-[11px] font-semibold opacity-70">
                            {message.sender_name}
                          </p>
                        )}
                        {editingId === message.id ? (
                          <div className="flex items-center gap-1">
                            <Input
                              autoFocus
                              value={editDraft}
                              onChange={(e) => setEditDraft(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") saveEdit(message.id);
                                if (e.key === "Escape") setEditingId(null);
                              }}
                              placeholder="Edit message…"
                            />
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => saveEdit(message.id)}
                            >
                              Save
                            </Button>
                          </div>
                        ) : message.deleted ? (
                          <p className="text-[13px] italic opacity-60">
                            Deleted message
                          </p>
                        ) : (
                          <p className="whitespace-pre-wrap text-[13px]">
                            {message.content}
                            {message.edited && (
                              <span
                                className={`ml-1 text-[11px] ${message.sender_id === myEmployeeId ? "text-white/70" : "text-faint"}`}
                              >
                                (edited)
                              </span>
                            )}
                          </p>
                        )}
                        <div
                          className={`mt-1 flex items-center gap-2 text-[11px] ${message.sender_id === myEmployeeId ? "text-white/70" : "text-faint"}`}
                        >
                          <span>{timeAgo(message.created_at)}</span>
                          <button
                            onClick={() => react(message, "👍")}
                            title="React"
                            className="flex items-center gap-0.5 hover:opacity-70"
                          >
                            <Smile className="h-3 w-3" />
                            {message.reaction_count > 0 && (
                              <span>{message.reaction_count}</span>
                            )}
                          </button>
                          <button
                            onClick={() => pin(message)}
                            title="Pin"
                            className="hover:opacity-70"
                          >
                            <Pin className="h-3 w-3" />
                          </button>
                          {!message.deleted &&
                            message.sender_id === myEmployeeId && (
                              <>
                                <button
                                  onClick={() => startEdit(message)}
                                  title="Edit"
                                  className="hover:opacity-70"
                                >
                                  <Pencil className="h-3 w-3" />
                                </button>
                                <button
                                  onClick={() => remove(message.id)}
                                  title="Delete"
                                  className="hover:opacity-70"
                                >
                                  <Trash2 className="h-3 w-3" />
                                </button>
                              </>
                            )}
                        </div>
                        {message.reactions.length > 0 && (
                          <div className="mt-1 flex gap-1">
                            {message.reactions.map((reaction) => (
                              <span
                                key={reaction.emoji}
                                className="rounded bg-white/20 px-1.5 py-0.5 text-[11px]"
                              >
                                {reaction.emoji} {reaction.count}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="flex items-center gap-2 border-t border-line p-3">
                <Input
                  placeholder="Type a message…"
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                />
                <Button size="sm" onClick={submit} loading={sending}>
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <EmptyState
                icon={Search}
                title="Select a conversation"
                description="Pick a conversation on the left, or start a new one."
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
