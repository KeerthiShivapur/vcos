"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Bot,
  CalendarPlus,
  ListChecks,
  Loader2,
  Mic,
  MicOff,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  User,
} from "lucide-react";

import {
  askCompanionStream,
  createPlan,
  getCompanionStatus,
  listRecommendations,
  submitFeedback,
} from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Badge } from "@/components/ui/Badge";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

export default function AiCompanionPage() {
  return (
    <Suspense fallback={null}>
      <CompanionContent />
    </Suspense>
  );
}

const SUGGESTIONS = [
  "What should I work on today?",
  "Give me the org pulse",
  "Plan my day",
  "Find an expert on design",
  "Search for onboarding",
  "What do you recommend for me?",
];

interface Message {
  id?: string;
  role: "user" | "assistant";
  content: string;
  source?: string;
  intents?: string[];
  rated?: boolean;
  stream?: boolean;
}

interface CompanionStatus {
  available: boolean;
  provider: string;
  mode?: string;
  message: string;
  capabilities: string[];
}

const SUPPORTED_SPEECH =
  typeof window !== "undefined" && !!(window as any).webkitSpeechRecognition;

function CompanionContent() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hi! I'm the AI Companion. I read the company's live work data to plan your day, summarize projects, tasks, goals and meetings, give the org pulse, find experts, and recommend what to do next.",
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<CompanionStatus | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(
    undefined,
  );
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getCompanionStatus()
      .then((s) => setStatus(s))
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function send(question?: string) {
    const text = (question ?? input).trim();
    if (!text || sending) return;
    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      let liveId: string | undefined;
      let intents: string[] = [];
      let source: "rules" | "llm" = "rules";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "", stream: true },
      ]);
      for await (const chunk of askCompanionStream(
        text,
        undefined,
        conversationId,
      )) {
        if (chunk.done) {
          liveId = chunk.done.conversation_id;
          intents = chunk.done.intents;
          source = chunk.done.source;
          setConversationId(chunk.done.conversation_id ?? conversationId);
        } else if (chunk.delta) {
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1
                ? { ...m, content: m.content + chunk.delta! }
                : m,
            ),
          );
        }
      }
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === "assistant" && last.stream) {
          next[next.length - 1] = {
            ...last,
            stream: false,
            id: undefined,
            source,
            intents,
          };
        }
        return next;
      });
      setConversationId(liveId ?? conversationId);
    } catch (err) {
      toastError(
        err instanceof Error ? err.message : "The Companion could not answer",
      );
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "I couldn't reach the backend. Please try again.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function runQuickAction(action: "plan" | "recommend") {
    if (sending) return;
    setSending(true);
    try {
      if (action === "plan") {
        const plan = await createPlan("daily");
        const content = [
          `Daily plan for ${plan.employee}:`,
          ...(plan.overdue?.length
            ? [`Overdue: ${plan.overdue.join(", ")}`]
            : []),
          `Focus: ${(plan.focus ?? []).join(", ") || "nothing scheduled"}`,
          plan.tasks?.length
            ? `Tasks (${plan.tasks.length}): ${plan.tasks.map((t) => t.title).join(", ")}`
            : "No open tasks.",
          plan.meetings?.length
            ? `Meetings: ${plan.meetings.map((m: any) => m.title).join(", ")}`
            : "No meetings today.",
        ];
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: content.join("\n"), source: "rules" },
        ]);
      } else {
        const data = await listRecommendations("user");
        const items = data.recommendations ?? [];
        if (!items.length) {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content:
                "I don't have recommendations for you yet — keep working and I'll learn what to suggest.",
              source: "rules",
            },
          ]);
        } else {
          const content = [
            "Here's what I recommend for you right now:",
            ...items.map(
              (r) => `- ${r.title}${r.summary ? `: ${r.summary}` : ""}`,
            ),
          ];
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: content.join("\n"), source: "rules" },
          ]);
        }
      }
    } catch (err) {
      toastError(err instanceof Error ? err.message : "The action failed");
    } finally {
      setSending(false);
    }
  }

  async function rate(message: Message, helpful: boolean) {
    if (!message.id || message.rated) return;
    try {
      await submitFeedback({ message_id: message.id, helpful });
      setMessages((prev) =>
        prev.map((m) => (m === message ? { ...m, rated: true } : m)),
      );
      toastSuccess("Thanks for the feedback!");
    } catch (err) {
      toastError("Could not save feedback");
    }
  }

  function toggleVoice() {
    const SpeechRecognition = (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      toastError("Speech recognition is not supported in this browser");
      return;
    }
    if (listening) {
      setListening(false);
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript as string;
      setInput(transcript);
      setListening(false);
    };
    recognition.onerror = () => {
      setListening(false);
      toastError("Could not hear you — try typing instead");
    };
    recognition.onend = () => setListening(false);
    setListening(true);
    recognition.start();
  }

  return (
    <div className="flex h-full flex-col space-y-6">
      <PageHeader
        title="AI Companion"
        description="Work intelligence grounded in your company's live data."
        actions={
          status ? (
            <div className="flex items-center gap-2">
              <Badge tone={status.available ? "success" : "neutral"}>
                {status.mode === "groq" ? "Groq LLM" : "Built-in engine"}
              </Badge>
              <Badge tone="neutral">{status.provider}</Badge>
            </div>
          ) : undefined
        }
      />

      {error && <ErrorState title="Companion unavailable" message={error} />}

      <Card bodyClassName="flex min-h-[420px] flex-1 flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex gap-3 ${message.role === "user" ? "flex-row-reverse" : ""}`}
            >
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${message.role === "user" ? "bg-brand-soft text-brand" : "bg-brand text-white"}`}
              >
                {message.role === "user" ? (
                  <User className="h-4 w-4" />
                ) : (
                  <Bot className="h-4 w-4" />
                )}
              </div>
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${message.role === "user" ? "rounded-tr-sm bg-brand text-white" : "rounded-tl-sm border border-line bg-surface text-ink"}`}
              >
                <p className="whitespace-pre-wrap">
                  {message.content}
                  {message.stream && (
                    <span className="animate-pulse text-brand">▍</span>
                  )}
                </p>
                {message.role === "assistant" &&
                  (message.source || message.intents) && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {message.source && (
                        <Badge tone="brand">
                          {message.source === "llm" ? "LLM" : "Grounded"}
                        </Badge>
                      )}
                      {(message.intents ?? []).map((intent) => (
                        <span
                          key={intent}
                          className="rounded bg-canvas px-1.5 py-0.5 text-[10px] font-medium text-faint"
                        >
                          {intent.replace("_", " ")}
                        </span>
                      ))}
                    </div>
                  )}
                {message.role === "assistant" && message.id && (
                  <div className="mt-2 flex items-center gap-1">
                    <button
                      onClick={() => rate(message, true)}
                      disabled={message.rated}
                      className="rounded p-1 text-faint transition-colors hover:bg-canvas hover:text-success disabled:opacity-40"
                      title="Helpful"
                    >
                      <ThumbsUp className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => rate(message, false)}
                      disabled={message.rated}
                      className="rounded p-1 text-faint transition-colors hover:bg-canvas hover:text-danger disabled:opacity-40"
                      title="Not helpful"
                    >
                      <ThumbsDown className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
          {sending && !messages[messages.length - 1]?.stream && (
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand text-white">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
              <span className="text-[13px] text-faint">
                Thinking about your company…
              </span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-line p-3">
          <div className="mb-2 flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => send(suggestion)}
                disabled={sending}
                className="rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] font-medium text-muted transition-colors hover:border-brand hover:text-brand"
              >
                {suggestion}
              </button>
            ))}
            <button
              onClick={() => runQuickAction("plan")}
              disabled={sending}
              className="flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] font-medium text-muted transition-colors hover:border-brand hover:text-brand"
              title="Generate your daily plan"
            >
              <CalendarPlus className="h-3 w-3" /> Plan my day
            </button>
            <button
              onClick={() => runQuickAction("recommend")}
              disabled={sending}
              className="flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] font-medium text-muted transition-colors hover:border-brand hover:text-brand"
              title="Get personalized recommendations"
            >
              <Sparkles className="h-3 w-3" /> Recommendations
            </button>
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
            className="flex items-center gap-2"
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask about your work, a project, or the company…"
              className="input h-10 flex-1"
            />
            {SUPPORTED_SPEECH && (
              <Button
                type="button"
                size="sm"
                variant={listening ? "primary" : "secondary"}
                onClick={toggleVoice}
                title={listening ? "Stop listening" : "Speak your question"}
              >
                {listening ? (
                  <MicOff className="h-4 w-4" />
                ) : (
                  <Mic className="h-4 w-4" />
                )}
              </Button>
            )}
            <Button
              type="submit"
              size="sm"
              loading={sending}
              disabled={!input.trim()}
            >
              <Send className="h-4 w-4" /> Ask
            </Button>
          </form>
        </div>
      </Card>

      <p className="text-[12px] text-faint">
        The Companion only answers with data from your organization. Ask for a
        summary on any project, task, goal or meeting page, or jump straight to
        one below —{" "}
        <Link href="/projects" className="font-medium text-brand">
          Projects
        </Link>{" "}
        ·{" "}
        <Link href="/tasks" className="font-medium text-brand">
          Tasks
        </Link>{" "}
        ·{" "}
        <Link href="/goals" className="font-medium text-brand">
          Goals
        </Link>{" "}
        ·{" "}
        <Link href="/meetings" className="font-medium text-brand">
          Meetings
        </Link>{" "}
        ·{" "}
        <Link href="/analytics" className="font-medium text-brand">
          Analytics
        </Link>
      </p>
    </div>
  );
}
