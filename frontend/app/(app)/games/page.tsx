"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import {
  Brain,
  Puzzle,
  Type,
  Lock,
  Users,
  Clock,
  ArrowRight,
  Play,
  Plus,
  Trophy,
} from "lucide-react";
import { api } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { toastSuccess, toastError } from "@/components/ui/Toaster";
import { formatDate } from "@/lib/utils";

type GameCatalogItem = {
  game_type: string;
  title: string;
  description: string;
  min_players: number;
  max_players: number;
  estimated_duration: string;
  tags: string[];
  icon: string;
};

type GameSession = {
  id: string;
  game_type: string;
  title: string;
  description: string | null;
  status: string;
  player_count: number;
  max_players: number;
  created_by: string;
  created_at: string;
  is_public: boolean;
};

export default function GamesPage() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.COMMUNICATION_MANAGE);

  const [catalog, setCatalog] = useState<GameCatalogItem[]>([]);
  const [sessions, setSessions] = useState<GameSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"catalog" | "sessions">("catalog");
  const [createOpen, setCreateOpen] = useState(false);
  const [createType, setCreateType] = useState<"trivia" | "puzzle">("trivia");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");

  useEffect(() => {
    loadCatalog();
    loadSessions();
  }, []);

  async function loadCatalog() {
    try {
      const data = await api<GameCatalogItem[]>("/games/catalog");
      setCatalog(data);
    } catch {
      /* ignore */
    }
  }

  async function loadSessions() {
    setLoading(true);
    setError(null);
    try {
      const data = await api<GameSession[]>("/games/sessions");
      setSessions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load games");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    if (!formTitle.trim()) {
      setFormError("Title is required");
      return;
    }
    setFormError(null);
    setCreating(true);
    try {
      if (createType === "trivia") {
        await api("/games/trivia", {
          method: "POST",
          body: { title: formTitle, description: formDescription || undefined },
        });
      } else {
        await api("/games/puzzle", {
          method: "POST",
          body: { title: formTitle, description: formDescription || undefined },
        });
      }
      toastSuccess(
        `${createType === "trivia" ? "Trivia" : "Puzzle"} game created`,
      );
      setCreateOpen(false);
      setFormTitle("");
      setFormDescription("");
      await loadSessions();
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Unable to create game",
      );
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <Spinner label="Loading games" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Joy & Break Layer"
        description="Games and activities to bring your team together."
        actions={
          canManage && (
            <Button
              onClick={() => {
                setCreateType("trivia");
                setCreateOpen(true);
              }}
            >
              <Plus className="h-4 w-4" /> New Trivia
            </Button>
          )
        }
      />

      <div className="flex gap-2 border-b border-line">
        <Button
          variant={activeTab === "catalog" ? "primary" : "ghost"}
          className="px-4 py-2"
          onClick={() => setActiveTab("catalog")}
        >
          <Brain className="h-4 w-4 mr-2" /> Game Catalog
        </Button>
        <Button
          variant={activeTab === "sessions" ? "primary" : "ghost"}
          className="px-4 py-2"
          onClick={() => setActiveTab("sessions")}
        >
          <Trophy className="h-4 w-4 mr-2" /> Active Sessions
          {sessions.length > 0 && <Badge tone="brand">{sessions.length}</Badge>}
        </Button>
      </div>

      {error && (
        <ErrorState
          title="Could not load games"
          message={error}
          onRetry={loadSessions}
        />
      )}

      {activeTab === "catalog" && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {catalog.map((game) => (
            <Card
              key={game.game_type}
              className="group hover:border-brand/40 hover:shadow-lg transition-all"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-soft/50 text-2xl">
                  {game.icon}
                </div>
                <div>
                  <h3 className="font-semibold text-ink">{game.title}</h3>
                  <p className="text-[12px] text-faint">
                    {game.estimated_duration}
                  </p>
                </div>
              </div>
              <p className="text-[13px] text-muted mb-3">{game.description}</p>
              <div className="flex flex-wrap gap-1.5 mb-4">
                {game.tags.map((tag) => (
                  <Badge key={tag} tone="neutral" className="text-[11px]">
                    {tag}
                  </Badge>
                ))}
              </div>
              <div className="flex items-center justify-between text-[12px] text-faint">
                <span className="flex items-center gap-1">
                  <Users className="h-3.5 w-3.5" /> {game.min_players}–
                  {game.max_players} players
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" /> {game.estimated_duration}
                </span>
              </div>
              <Button
                className="mt-3 w-full"
                variant={
                  createType === "trivia" && game.game_type === "trivia"
                    ? "primary"
                    : createType === "puzzle" && game.game_type === "puzzle"
                      ? "primary"
                      : "secondary"
                }
                size="sm"
                onClick={() => {
                  setCreateType(
                    game.game_type === "trivia" ? "trivia" : "puzzle",
                  );
                  setCreateOpen(true);
                }}
              >
                {game.game_type === "trivia"
                  ? "Create Trivia"
                  : game.game_type === "puzzle"
                    ? "Create Puzzle"
                    : "Not Implemented"}
              </Button>
            </Card>
          ))}
        </div>
      )}

      {activeTab === "sessions" && (
        <>
          <div className="flex flex-wrap items-center gap-2 mb-4">
            {canManage && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setCreateType("trivia");
                  setCreateOpen(true);
                }}
              >
                <Plus className="h-4 w-4" /> New Trivia
              </Button>
            )}
            {canManage && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setCreateType("puzzle");
                  setCreateOpen(true);
                }}
              >
                <Plus className="h-4 w-4" /> New Puzzle
              </Button>
            )}
          </div>
          {error ? (
            <ErrorState
              title="Could not load sessions"
              message={error}
              onRetry={loadSessions}
            />
          ) : loading ? (
            <div className="flex justify-center py-24">
              <Spinner label="Loading sessions" />
            </div>
          ) : sessions.length === 0 ? (
            <EmptyState
              icon={Trophy}
              title="No game sessions yet"
              description="Create a trivia game or puzzle to get started."
              action={
                canManage ? (
                  <Button
                    size="sm"
                    onClick={() => {
                      setCreateType("trivia");
                      setCreateOpen(true);
                    }}
                  >
                    <Plus className="h-4 w-4" /> Create Trivia
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {sessions.map((session) => (
                <Card
                  key={session.id}
                  className="hover:border-brand/40 transition"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-lg">
                      {session.game_type === "trivia"
                        ? "🧠"
                        : session.game_type === "puzzle"
                          ? "🧩"
                          : "🎮"}
                    </div>
                    <Badge
                      tone={
                        session.status === "active"
                          ? "success"
                          : session.status === "waiting"
                            ? "brand"
                            : session.status === "completed"
                              ? "success"
                              : "neutral"
                      }
                    >
                      {session.status}
                    </Badge>
                  </div>
                  <h3 className="mt-3 truncate text-[15px] font-semibold text-ink">
                    {session.title}
                  </h3>
                  {session.description && (
                    <p className="mt-1 line-clamp-2 text-[13px] text-muted">
                      {session.description}
                    </p>
                  )}
                  <div className="mt-3 flex items-center gap-3 text-[12px] text-faint">
                    <span className="flex items-center gap-1">
                      <Users className="h-3.5 w-3.5" /> {session.player_count}/
                      {session.max_players}
                    </span>
                    <span>{formatDate(session.created_at)}</span>
                  </div>
                  <div className="mt-3 pt-3 border-t border-line flex gap-2">
                    <Link
                      href={
                        session.game_type === "trivia"
                          ? `/games/trivia/${session.id}`
                          : `/games/puzzle/${session.id}`
                      }
                    >
                      <Button variant="ghost" size="sm" className="flex-1">
                        {session.status === "waiting"
                          ? "Join"
                          : session.status === "active"
                            ? "Play"
                            : "View Results"}
                        <ArrowRight className="h-3.5 w-3.5 ml-1" />
                      </Button>
                    </Link>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      <CreateGameModal
        open={createOpen}
        onClose={() => {
          setCreateOpen(false);
          setFormTitle("");
          setFormDescription("");
          setFormError(null);
        }}
        onCreate={handleCreate}
        creating={creating}
        gameType={createType}
        title={formTitle}
        setTitle={setFormTitle}
        description={formDescription}
        setDescription={setFormDescription}
        error={formError}
      />
    </div>
  );
}

function CreateGameModal({
  open,
  onClose,
  onCreate,
  creating,
  gameType,
  title,
  setTitle,
  description,
  setDescription,
  error,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: () => Promise<void>;
  creating: boolean;
  gameType: "trivia" | "puzzle";
  title: string;
  setTitle: (v: string) => void;
  description: string;
  setDescription: (v: string) => void;
  error: string | null;
}) {
  const modalTitle =
    gameType === "trivia" ? "Create Trivia Game" : "Create Puzzle Game";
  const modalDescription =
    gameType === "trivia"
      ? "Create a quick trivia game for your team. Questions will be auto-generated."
      : "Create a collaborative puzzle for your team to solve together.";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={modalTitle}
      description={modalDescription}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={onCreate} loading={creating}>
            Create
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="Title"
          placeholder="e.g. Friday Fun Trivia"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
        <Textarea
          label="Description (optional)"
          placeholder="What's this game about?"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
        />
        {error && <p className="text-[13px] text-danger">{error}</p>}
        <p className="text-[12px] text-faint">
          {gameType === "trivia"
            ? "Auto-generates 5 trivia questions across categories. 30 seconds per question. 2-20 players."
            : "Creates a collaborative crossword puzzle. Work together to solve it. 1-10 players."}
        </p>
      </div>
    </Modal>
  );
}
