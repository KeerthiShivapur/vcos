"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { Pin, Search, Send, Smile } from "lucide-react";

import {
  archiveConversation,
  createConversation,
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
  const listRef = useRef<HTMLDivElement>(null);

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
      setError(err instanceof Error ? err.message : "Unable to load conversations");
    }
  }

  async function openConversation(id: string) {
    setActiveId(id);
    setLoading(true);
    try {
      const [list, mentionList] = await Promise.all([listMessages(id), listMyMentions(20)]);
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
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, activeId]);

  async function startDm(employeeId: string) {
    try {
      const conversation = await openDm(employeeId);
      await loadConversations();
      await openConversation(conversation.id);
      setTab("conversations");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to open conversation");
    }
  }

  async function startChannel() {
    try {
      const conversation = await createConversation({ type: "channel", title: "General", channel_kind: "general", channel_key: "general" });
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
                      {conversation.title ?? (conversation.type === "channel" ? "# " : "") + "Direct message"}
                    </p>
                    {conversation.unread_count > 0 && <Badge tone="brand">{conversation.unread_count}</Badge>}
                  </div>
                  <p className="truncate text-[12px] text-faint">
                    {conversation.type} · {conversation.message_count} messages
                  </p>
                </button>
              ))}
              <div className="mt-2 border-t border-line pt-2">
                <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-faint">Start a DM</p>
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
                      <span className="truncate text-[13px] text-muted">{employee.full_name}</span>
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
                    <p className="truncate text-[13px] text-ink">{mention.sender_name} mentioned you</p>
                    <p className="truncate text-[12px] text-faint">{mention.content}</p>
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
                  <p className="text-sm font-semibold text-ink">{active.title ?? "Direct message"}</p>
                  <p className="text-[12px] text-faint">
                    {active.type} · {active.member_count} members
                  </p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => archiveConversation(active.id).then(loadConversations)}>
                  Archive
                </Button>
              </div>

              <div ref={listRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
                {loading ? (
                  <div className="flex justify-center py-12"><Spinner label="Loading messages" /></div>
                ) : messages.length === 0 ? (
                  <EmptyState title="No messages yet" description="Say hello to get things started." />
                ) : (
                  messages.map((message) => (
                    <div key={message.id} className={`flex gap-2 ${message.sender_id === myEmployeeId ? "flex-row-reverse" : ""}`}>
                      <div className={`max-w-[70%] rounded-lg px-3 py-2 ${message.sender_id === myEmployeeId ? "bg-brand text-white" : "bg-surface-muted text-ink"}`}>
                        {message.sender_id !== myEmployeeId && (
                          <p className="text-[11px] font-semibold opacity-70">{message.sender_name}</p>
                        )}
                        {message.deleted ? (
                          <p className="text-[13px] italic opacity-60">Deleted message</p>
                        ) : (
                          <p className="whitespace-pre-wrap text-[13px]">{message.content}</p>
                        )}
                        <div className={`mt-1 flex items-center gap-2 text-[11px] ${message.sender_id === myEmployeeId ? "text-white/70" : "text-faint"}`}>
                          <span>{timeAgo(message.created_at)}</span>
                          <button
                            onClick={() => react(message, "👍")}
                            title="React"
                            className="flex items-center gap-0.5 hover:opacity-70"
                          >
                            <Smile className="h-3 w-3" />
                            {message.reaction_count > 0 && <span>{message.reaction_count}</span>}
                          </button>
                          <button onClick={() => pin(message)} title="Pin" className="hover:opacity-70">
                            <Pin className="h-3 w-3" />
                          </button>
                        </div>
                        {message.reactions.length > 0 && (
                          <div className="mt-1 flex gap-1">
                            {message.reactions.map((reaction) => (
                              <span key={reaction.emoji} className="rounded bg-white/20 px-1.5 py-0.5 text-[11px]">
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
