"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  Brain,
  Users,
  Trophy,
  Clock,
  CheckCircle,
  XCircle,
  ArrowLeft,
  Play,
  Pause,
  SkipForward,
  Volume2,
  VolumeX,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Progress } from "@/components/ui/Progress";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Modal } from "@/components/ui/Modal";
import { Avatar } from "@/components/ui/Avatar";
import { toastSuccess, toastError } from "@/components/ui/Toaster";
import { formatDate } from "@/lib/utils";

type TriviaQuestion = {
  id: string;
  question: string;
  options: string[];
  correct_answer: number;
  category: string;
  difficulty: string;
  points: number;
  explanation: string | null;
};

type TriviaPlayer = {
  player_id: string;
  player_name: string;
  score: number;
  correct_count: number;
  answers: TriviaAnswer[];
};

type TriviaAnswer = {
  question_index: number;
  answer: number;
  is_correct: boolean;
  points_earned: number;
  time_taken: number;
  correct_answer: number;
  explanation: string | null;
};

type TriviaSession = {
  id: string;
  organization_id: string;
  game_type: string;
  title: string;
  description: string | null;
  questions: TriviaQuestion[];
  time_per_question: number;
  max_players: number;
  is_public: boolean;
  status: string;
  current_question: number;
  created_by: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

type TriviaSessionState = {
  session: TriviaSession;
  players: TriviaPlayer[];
  current_question: TriviaQuestion | null;
  time_remaining: number;
  is_host: boolean;
  can_join: boolean;
};

export default function TriviaGamePage() {
  const router = useRouter();
  const params = useParams();
  const sessionId = params.id as string;
  const { user } = useAuth();

  const [state, setState] = useState<TriviaSessionState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAnswer, setSelectedAnswer] = useState<number | null>(null);
  const [answerSubmitted, setAnswerSubmitted] = useState(false);
  const [answerResult, setAnswerResult] = useState<TriviaAnswer | null>(null);
  const [timer, setTimer] = useState(0);
  const [showResults, setShowResults] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(true);

  const sortedPlayers = (state?.players || [])
    .slice()
    .sort((a: TriviaPlayer, b: TriviaPlayer) => b.score - a.score);

  useEffect(() => {
    loadSession();
    const interval = setInterval(() => {
      if (state?.session.status === "active" && timer > 0) {
        setTimer((t) => t - 1);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [sessionId, state?.session.status, timer]);

  async function loadSession() {
    setLoading(true);
    setError(null);
    try {
      const data = await api<TriviaSessionState>(`/games/trivia/${sessionId}`);
      setState(data);
      if (data.session.status === "active" && data.current_question) {
        setTimer(data.time_remaining);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load game");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (
      state?.session.status === "active" &&
      state.current_question &&
      !answerSubmitted &&
      timer <= 0
    ) {
      // Auto-submit when time runs out
      submitAnswer(-1); // -1 indicates timeout
    }
  }, [timer, state?.session.status, state?.current_question, answerSubmitted]);

  async function joinSession() {
    try {
      await api(`/games/trivia/${sessionId}/join`, { method: "POST" });
      toastSuccess("Joined game!");
      await loadSession();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to join");
    }
  }

  async function startSession() {
    try {
      await api(`/games/trivia/${sessionId}/start`, { method: "POST" });
      toastSuccess("Game started!");
      await loadSession();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to start");
    }
  }

  async function submitAnswer(answer: number) {
    if (answerSubmitted || !state?.current_question) return;
    setAnswerSubmitted(true);
    setSelectedAnswer(answer);

    const timeTaken = state?.session.time_per_question - timer;
    try {
      const result = await api<TriviaAnswer>(
        `/games/trivia/${sessionId}/answer`,
        {
          method: "POST",
          body: {
            question_index: state.session.current_question,
            answer,
            time_taken: timeTaken,
          },
        },
      );
      setAnswerResult(result);
      if (soundEnabled) playSound(result.is_correct);
      await loadSession();
      setShowResults(true);
    } catch (err) {
      toastError(
        err instanceof Error ? err.message : "Unable to submit answer",
      );
      setAnswerSubmitted(false);
    }
  }

  async function nextQuestion() {
    try {
      await api(`/games/trivia/${sessionId}/next`, { method: "POST" });
      setAnswerSubmitted(false);
      setSelectedAnswer(null);
      setAnswerResult(null);
      setShowResults(false);
      await loadSession();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to advance");
    }
  }

  function playSound(correct: boolean) {
    // Simple beep using Web Audio API
    try {
      const ctx = new (
        window.AudioContext || (window as any).webkitAudioContext
      )();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.value = correct ? 880 : 220;
      gain.gain.value = 0.1;
      osc.start();
      osc.stop(ctx.currentTime + 0.2);
    } catch {
      // Ignore audio errors
    }
  }

  function getDifficultyColor(difficulty: string) {
    switch (difficulty) {
      case "easy":
        return "success";
      case "medium":
        return "warning";
      case "hard":
        return "danger";
      default:
        return "neutral";
    }
  }

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <Spinner label="Loading game" />
      </div>
    );
  }

  if (error)
    return (
      <ErrorState
        title="Could not load game"
        message={error}
        onRetry={loadSession}
      />
    );

  if (!state)
    return (
      <EmptyState
        icon={Brain}
        title="Game not found"
        description="This trivia session doesn't exist."
      />
    );

  const {
    session,
    players,
    current_question,
    time_remaining,
    is_host,
    can_join,
  } = state;
  const isPlayer = players.some((p) => p.player_id === user?.id);
  const currentPlayer = players.find((p) => p.player_id === user?.id);

  if (session.status === "waiting") {
    return (
      <div className="space-y-6">
        <PageHeader
          title={session.title}
          description={session.description || "Waiting for players to join..."}
          actions={
            <>
              {can_join && !isPlayer && (
                <Button onClick={joinSession}>
                  <Users className="h-4 w-4 mr-2" /> Join Game
                </Button>
              )}
              {is_host && isPlayer && (
                <Button onClick={startSession}>
                  <Play className="h-4 w-4 mr-2" /> Start Game
                </Button>
              )}
            </>
          }
        />

        <div className="grid gap-4 md:grid-cols-3">
          <Card className="p-5">
            <h3 className="font-semibold text-ink mb-3">Game Details</h3>
            <dl className="space-y-2 text-[13px]">
              <div className="flex justify-between">
                <dt className="text-faint">Questions</dt>
                <dd className="font-medium text-ink">
                  {session.questions.length}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-faint">Time per question</dt>
                <dd className="font-medium text-ink">
                  {session.time_per_question}s
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-faint">Max players</dt>
                <dd className="font-medium text-ink">{session.max_players}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-faint">Status</dt>
                <dd>
                  <Badge tone="brand">{session.status}</Badge>
                </dd>
              </div>
            </dl>
          </Card>

          <Card className="p-5">
            <h3 className="font-semibold text-ink mb-3">
              Players ({players.length}/{session.max_players})
            </h3>
            {players.length === 0 ? (
              <p className="text-faint">No players yet</p>
            ) : (
              <ul className="space-y-2">
                {sortedPlayers.map((player, index) => (
                  <li
                    key={player.player_id}
                    className="flex items-center gap-2"
                  >
                    <span className="w-6 text-center font-bold text-faint">
                      {index + 1}
                    </span>
                    <Avatar name={player.player_name} size="sm" />
                    <span className="font-medium text-ink">
                      {player.player_name}
                    </span>
                    {player.player_id === session.created_by && (
                      <Badge tone="brand" className="ml-auto text-[10px]">
                        Host
                      </Badge>
                    )}
                    {player.player_id === user?.id && (
                      <Badge tone="success" className="ml-auto text-[10px]">
                        You
                      </Badge>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="p-5">
            <h3 className="font-semibold text-ink mb-3">How to Play</h3>
            <ul className="space-y-2 text-[13px] text-muted">
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-success" /> Answer each
                question within {session.time_per_question} seconds
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-success" /> Correct answers
                earn points based on difficulty
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-success" /> Fastest correct
                answers get bonus points
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-success" /> Host advances
                to next question
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-success" /> Game ends after
                all questions
              </li>
            </ul>
          </Card>
        </div>
      </div>
    );
  }

  if (session.status === "completed") {
    return (
      <div className="space-y-6">
        <PageHeader
          title={session.title}
          description="Game completed! Final standings:"
        />

        <Card className="p-5">
          <h3 className="font-semibold text-ink mb-4">Final Leaderboard</h3>
          <div className="space-y-2">
            {sortedPlayers.map((player, index) => (
              <div
                key={player.player_id}
                className="flex items-center gap-3 p-3 rounded-lg bg-surface border border-line"
              >
                <span className="w-10 text-center text-2xl font-bold text-brand">
                  {index + 1}
                </span>
                <Avatar name={player.player_name} size="md" />
                <div className="flex-1">
                  <p className="font-semibold text-ink">{player.player_name}</p>
                  <p className="text-[12px] text-faint">
                    {player.correct_count}/{session.questions.length} correct
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xl font-bold text-ink">
                    {player.score} pts
                  </p>
                  <p className="text-[12px] text-faint">
                    {player.answers.filter((a) => a.is_correct).length} correct
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => router.push("/games")}>
            <ArrowLeft className="h-4 w-4 mr-2" /> Back to Games
          </Button>
          {is_host && (
            <Button
              onClick={async () => {
                await api(`/games/trivia/${sessionId}`, { method: "DELETE" });
                router.push("/games");
              }}
              variant="danger"
            >
              Delete Session
            </Button>
          )}
        </div>
      </div>
    );
  }

  // Active game
  const question = current_question;
  const progress =
    session.questions.length > 0
      ? (session.current_question / session.questions.length) * 100
      : 0;
  const isAnswered = answerSubmitted;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[12px] text-faint">
            Question {session.current_question + 1} of{" "}
            {session.questions.length}
          </p>
          <h1 className="text-xl font-bold text-ink">{session.title}</h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Volume2
              className="h-4 w-4"
              onClick={() => setSoundEnabled(!soundEnabled)}
              style={{ cursor: "pointer", opacity: soundEnabled ? 1 : 0.5 }}
            />
            {soundEnabled ? (
              <Volume2 className="h-4 w-4" />
            ) : (
              <VolumeX className="h-4 w-4" />
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/games")}
          >
            <ArrowLeft className="h-4 w-4 mr-2" /> Leave
          </Button>
        </div>
      </div>

      <Progress value={progress} className="h-3" />

      {question && (
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <Badge tone={getDifficultyColor(question.difficulty)}>
              {question.difficulty}
            </Badge>
            <Badge tone="brand">{question.category}</Badge>
            <Badge tone="neutral">{question.points} pts</Badge>
          </div>

          <p className="text-lg font-semibold text-ink mb-6">
            {question.question}
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            {question.options.map((option, index) => (
              <Button
                key={index}
                variant={
                  isAnswered
                    ? index === question.correct_answer
                      ? "primary"
                      : index === selectedAnswer
                        ? "danger"
                        : "secondary"
                    : "secondary"
                }
                className="h-16 text-left justify-start font-medium"
                disabled={isAnswered}
                onClick={() => !isAnswered && submitAnswer(index)}
              >
                <span className="mr-2 font-mono text-lg">
                  {String.fromCharCode(65 + index)}.
                </span>
                {option}
              </Button>
            ))}
          </div>

          {isAnswered && answerResult && (
            <div className="mt-6 p-4 rounded-lg border border-line bg-canvas">
              <div className="flex items-center gap-3 mb-2">
                {answerResult.is_correct ? (
                  <CheckCircle className="h-6 w-6 text-success" />
                ) : (
                  <XCircle className="h-6 w-6 text-danger" />
                )}
                <div>
                  <p className="font-semibold text-ink">
                    {answerResult.is_correct ? "Correct!" : "Incorrect"}
                    {answerResult.points_earned > 0 && (
                      <span className="ml-2 text-brand">
                        +{answerResult.points_earned} pts
                      </span>
                    )}
                  </p>
                  <p className="text-[13px] text-muted">
                    The correct answer was{" "}
                    <strong>
                      {String.fromCharCode(65 + answerResult.correct_answer)}.{" "}
                      {question.options[answerResult.correct_answer]}
                    </strong>
                  </p>
                </div>
              </div>
              {answerResult.explanation && (
                <p className="mt-3 text-[13px] text-faint">
                  <strong>Explanation:</strong> {answerResult.explanation}
                </p>
              )}
            </div>
          )}

          {!isAnswered && (
            <div className="mt-6 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Clock className="h-5 w-5 text-brand" />
                <span className="text-lg font-mono font-bold text-brand">
                  {timer}s
                </span>
              </div>
              <Progress
                value={(timer / session.time_per_question) * 100}
                className="flex-1 max-w-xs h-2"
              />
            </div>
          )}

          {isAnswered && is_host && (
            <Button className="mt-6 w-full" size="md" onClick={nextQuestion}>
              <SkipForward className="h-4 w-4 mr-2" /> Next Question
            </Button>
          )}
        </Card>
      )}

      <Card className="p-4">
        <h3 className="font-semibold text-ink mb-3">Live Leaderboard</h3>
        <div className="space-y-2">
          {sortedPlayers.map((player, index) => (
            <div
              key={player.player_id}
              className="flex items-center gap-3 p-2 rounded-lg bg-surface border border-line"
            >
              <span className="w-8 text-center font-bold text-faint">
                {index + 1}
              </span>
              <Avatar name={player.player_name} size="sm" />
              <span className="flex-1 font-medium text-ink">
                {player.player_name}
              </span>
              <span className="text-[12px] text-faint">
                {player.correct_count}/{session.questions.length} correct
              </span>
              <span className="text-lg font-bold text-ink">
                {player.score} pts
              </span>
              {player.player_id === user?.id && (
                <Badge tone="success" className="ml-auto text-[10px]">
                  You
                </Badge>
              )}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
