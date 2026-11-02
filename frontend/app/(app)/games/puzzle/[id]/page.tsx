"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  Puzzle,
  Users,
  CheckCircle,
  ArrowLeft,
  RotateCcw,
  Lightbulb,
  Zap,
  Flag,
  Trophy,
} from "lucide-react";
import { classNames } from "@/lib/utils";
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

type PuzzleData = {
  type: string;
  grid_size: number;
  clues: {
    across: Record<string, string>;
    down: Record<string, string>;
  };
  solution: string[][];
  hints_enabled: boolean;
};

type PuzzleSession = {
  id: string;
  organization_id: string;
  game_type: string;
  title: string;
  description: string | null;
  puzzle_data: PuzzleData;
  max_players: number;
  time_limit: number | null;
  is_public: boolean;
  status: string;
  progress: { completed_cells: number; total_cells: number };
  created_by: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

type PuzzlePlayer = {
  player_id: string;
  player_name: string;
};

type PuzzleState = {
  session: PuzzleSession;
  players: PuzzlePlayer[];
  progress: { completed_cells: number; total_cells: number };
};

export default function PuzzleGamePage() {
  const router = useRouter();
  const params = useParams();
  const sessionId = params.id as string;
  const { user } = useAuth();

  const [state, setState] = useState<PuzzleState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [grid, setGrid] = useState<string[][]>([]);
  const [selectedCell, setSelectedCell] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const [showHints, setShowHints] = useState(true);
  const [completed, setCompleted] = useState(false);
  const [timer, setTimer] = useState(0);

  useEffect(() => {
    loadSession();
    const interval = setInterval(() => {
      if (state?.session.status === "active" && state.session.time_limit) {
        setTimer((t) => t + 1);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [sessionId, state?.session.status, state?.session.time_limit]);

  async function loadSession() {
    setLoading(true);
    setError(null);
    try {
      const data = await api<PuzzleState>(`/games/puzzle/${sessionId}`);
      setState(data);
      if (data.session.puzzle_data) {
        initializeGrid(data.session.puzzle_data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load puzzle");
    } finally {
      setLoading(false);
    }
  }

  function initializeGrid(puzzleData: PuzzleData) {
    const size = puzzleData.grid_size;
    const emptyGrid: string[][] = Array(size)
      .fill(null)
      .map(() => Array(size).fill(""));
    setGrid(emptyGrid);
  }

  useEffect(() => {
    if (state?.session.status === "completed" && !completed) {
      setCompleted(true);
    }
  }, [state?.session.status, completed]);

  async function submitAction(actionType: string, payload: any) {
    try {
      const result = await api<PuzzleSession>(
        `/games/puzzle/${sessionId}/action`,
        {
          method: "POST",
          body: { action_type: actionType, payload },
        },
      );
      setState((prev) =>
        prev ? { ...prev, session: result, progress: result.progress } : null,
      );
      if (result.progress.completed_cells >= result.progress.total_cells) {
        setCompleted(true);
      }
    } catch (err) {
      toastError(
        err instanceof Error ? err.message : "Unable to submit action",
      );
    }
  }

  function handleCellClick(row: number, col: number) {
    if (state?.session.status !== "active") return;
    setSelectedCell({ row, col });
  }

  function handleKeyDown(e: React.KeyboardEvent, row: number, col: number) {
    if (state?.session.status !== "active") return;
    const char = e.key.toUpperCase();
    if (/^[A-Z]$/.test(char)) {
      const newGrid = grid.map((r, i) =>
        r.map((c, j) => (i === row && j === col ? char : c)),
      );
      setGrid(newGrid);
      submitAction("fill_cell", { row, col, value: char });
      // Auto-move to next cell
      if (col + 1 < grid[0].length) {
        setSelectedCell({ row, col: col + 1 });
      } else if (row + 1 < grid.length) {
        setSelectedCell({ row: row + 1, col: 0 });
      }
    } else if (e.key === "Backspace") {
      const newGrid = grid.map((r, i) =>
        r.map((c, j) => (i === row && j === col ? "" : c)),
      );
      setGrid(newGrid);
      submitAction("fill_cell", { row, col, value: "" });
    } else if (e.key === "ArrowRight" && col + 1 < grid[0].length) {
      setSelectedCell({ row, col: col + 1 });
    } else if (e.key === "ArrowLeft" && col - 1 >= 0) {
      setSelectedCell({ row, col: col - 1 });
    } else if (e.key === "ArrowDown" && row + 1 < grid.length) {
      setSelectedCell({ row: row + 1, col });
    } else if (e.key === "ArrowUp" && row - 1 >= 0) {
      setSelectedCell({ row: row - 1, col });
    }
  }

  function checkSolution() {
    if (!state?.session.puzzle_data) return;
    const solution = state.session.puzzle_data.solution;
    let correct = 0;
    for (let r = 0; r < solution.length; r++) {
      for (let c = 0; c < solution[r].length; c++) {
        if (grid[r][c].toUpperCase() === solution[r][c]) {
          correct++;
        }
      }
    }
    return correct === state.progress.total_cells;
  }

  function formatTime(seconds: number) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  const isPlayer = state?.players.some((p) => p.player_id === user?.id);
  const isHost = state?.session.created_by === user?.id;

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <Spinner label="Loading puzzle" />
      </div>
    );
  }

  if (error)
    return (
      <ErrorState
        title="Could not load puzzle"
        message={error}
        onRetry={loadSession}
      />
    );

  if (!state)
    return (
      <EmptyState
        icon={Puzzle}
        title="Puzzle not found"
        description="This puzzle session doesn't exist."
      />
    );

  const { session, players, progress } = state;
  const puzzleData = session.puzzle_data;
  const progressPercent =
    progress.total_cells > 0
      ? (progress.completed_cells / progress.total_cells) * 100
      : 0;

  if (session.status === "waiting") {
    return (
      <div className="space-y-6">
        <PageHeader
          title={session.title}
          description={
            session.description ||
            "Collaborative puzzle - work together to solve!"
          }
          actions={
            <>
              {isPlayer && !isHost && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    /* already in */
                  }}
                >
                  <Users className="h-4 w-4 mr-2" /> In Game
                </Button>
              )}
              {isHost && (
                <Button onClick={() => submitAction("start", {})}>
                  <Zap className="h-4 w-4 mr-2" /> Start Puzzle
                </Button>
              )}
            </>
          }
        />

        <div className="grid gap-4 md:grid-cols-2">
          <Card className="p-5">
            <h3 className="font-semibold text-ink mb-3">Puzzle Details</h3>
            <dl className="space-y-2 text-[13px]">
              <div className="flex justify-between">
                <dt className="text-faint">Type</dt>
                <dd className="font-medium text-ink capitalize">
                  {puzzleData?.type || "crossword"}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-faint">Grid Size</dt>
                <dd className="font-medium text-ink">
                  {puzzleData?.grid_size || 5}×{puzzleData?.grid_size || 5}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-faint">Total Cells</dt>
                <dd className="font-medium text-ink">{progress.total_cells}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-faint">Time Limit</dt>
                <dd className="font-medium text-ink">
                  {session.time_limit
                    ? `${session.time_limit} min`
                    : "No limit"}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-faint">Max Players</dt>
                <dd className="font-medium text-ink">{session.max_players}</dd>
              </div>
            </dl>
          </Card>

          <Card className="p-5">
            <h3 className="font-semibold text-ink mb-3">
              Players ({players.length}/{session.max_players})
            </h3>
            <ul className="space-y-2">
              {players.map((player, index) => (
                <li key={player.player_id} className="flex items-center gap-2">
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
          </Card>

          {puzzleData && (
            <Card className="p-5 md:col-span-2">
              <h3 className="font-semibold text-ink mb-3">Clues</h3>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h4 className="font-medium text-ink mb-2">Across</h4>
                  <ul className="space-y-1 text-[13px] text-muted">
                    {Object.entries(puzzleData.clues.across).map(
                      ([num, clue]) => (
                        <li key={num} className="flex gap-2">
                          <span className="font-mono text-brand">{num}.</span>
                          {clue}
                        </li>
                      ),
                    )}
                  </ul>
                </div>
                <div>
                  <h4 className="font-medium text-ink mb-2">Down</h4>
                  <ul className="space-y-1 text-[13px] text-muted">
                    {Object.entries(puzzleData.clues.down).map(
                      ([num, clue]) => (
                        <li key={num} className="flex gap-2">
                          <span className="font-mono text-brand">{num}.</span>
                          {clue}
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    );
  }

  if (session.status === "completed" || completed) {
    const solved = checkSolution();
    return (
      <div className="space-y-6">
        <PageHeader
          title={session.title}
          description={solved ? "Puzzle solved! 🎉" : "Time's up!"}
        />

        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-xl font-bold text-ink">
                {solved ? "Solved!" : "Completed"}
              </h3>
              <p className="text-muted">
                {progress.completed_cells}/{progress.total_cells} cells filled
              </p>
            </div>
            <Badge tone={solved ? "success" : "warning"} className="text-lg">
              {solved ? "Complete" : "Incomplete"}
            </Badge>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="p-4 rounded-lg bg-surface border border-line">
              <h4 className="font-medium text-ink mb-2">Your Solution</h4>
              <div className="font-mono text-sm space-y-1">
                {grid.map((row) => (
                  <div key={row.join("")}>
                    {row.map((c) => c || "·").join(" ")}
                  </div>
                ))}
              </div>
            </div>
            <div className="p-4 rounded-lg bg-surface border border-line">
              <h4 className="font-medium text-ink mb-2">Correct Solution</h4>
              <div className="font-mono text-sm space-y-1">
                {puzzleData?.solution.map((row) => (
                  <div key={row.join("")}>{row.join(" ")}</div>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-4 flex gap-2">
            <Button variant="secondary" onClick={() => router.push("/games")}>
              <ArrowLeft className="h-4 w-4 mr-2" /> Back to Games
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setGrid(grid.map((r) => r.map(() => "")));
                submitAction("reset", {});
              }}
            >
              <RotateCcw className="h-4 w-4 mr-2" /> Play Again
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  // Active puzzle
  const clues = puzzleData?.clues || { across: {}, down: {} };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[12px] text-faint">Collaborative Puzzle</p>
          <h1 className="text-xl font-bold text-ink">{session.title}</h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Flag className="h-4 w-4" />
            <span className="text-lg font-mono font-bold text-brand">
              {session.time_limit
                ? formatTime(session.time_limit * 60 - timer)
                : formatTime(timer)}
            </span>
          </div>
          <Progress value={progressPercent} className="w-48 h-2" />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/games")}
          >
            <ArrowLeft className="h-4 w-4 mr-2" /> Leave
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card className="p-4">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-semibold text-ink">Grid</h3>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowHints(!showHints)}
              >
                <Lightbulb className="h-4 w-4" /> Hints
              </Button>
              {checkSolution() && (
                <Badge tone="success">
                  <CheckCircle className="h-3 w-3 mr-1" /> Solved!
                </Badge>
              )}
            </div>
          </div>

          <div
            className="grid gap-1"
            style={{
              gridTemplateColumns: `repeat(${puzzleData?.grid_size || 5}, 1fr)`,
            }}
          >
            {grid.map((row, r) =>
              row.map((cell, c) => (
                <input
                  key={`${r}-${c}`}
                  type="text"
                  maxLength={1}
                  value={cell}
                  onChange={() => {}}
                  onKeyDown={(e) => handleKeyDown(e, r, c)}
                  onClick={() => handleCellClick(r, c)}
                  className={classNames(
                    "w-10 h-10 text-center text-lg font-bold border-2 rounded",
                    selectedCell?.row === r && selectedCell?.col === c
                      ? "border-brand bg-brand-soft"
                      : "border-line bg-surface",
                    checkSolution() && "text-success",
                  )}
                  style={{ textTransform: "uppercase" }}
                  disabled={completed}
                />
              )),
            )}
          </div>

          {selectedCell && (
            <div className="mt-4 p-3 rounded-lg bg-brand-soft/50 border border-brand/20">
              <p className="font-medium text-ink">
                Selected: {String.fromCharCode(65 + selectedCell.row)}
                {selectedCell.col + 1}
              </p>
              <p className="text-[13px] text-muted">
                Type a letter or use arrow keys to navigate
              </p>
            </div>
          )}
        </Card>

        <Card className="p-4">
          <h3 className="font-semibold text-ink mb-3">Clues</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h4 className="font-medium text-ink mb-2">Across</h4>
              <ul className="space-y-1 text-[13px] text-muted max-h-60 overflow-y-auto">
                {Object.entries(clues.across).map(([num, clue]) => (
                  <li key={num} className="flex gap-2">
                    <span className="font-mono text-brand">{num}.</span>
                    {clue}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="font-medium text-ink mb-2">Down</h4>
              <ul className="space-y-1 text-[13px] text-muted max-h-60 overflow-y-auto">
                {Object.entries(clues.down).map(([num, clue]) => (
                  <li key={num} className="flex gap-2">
                    <span className="font-mono text-brand">{num}.</span>
                    {clue}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[13px] text-faint">Progress</span>
              <Progress value={progressPercent} className="w-48 h-2" />
              <span className="text-[13px] font-mono text-brand">
                {progress.completed_cells}/{progress.total_cells}
              </span>
            </div>
            <div className="flex gap-2">
              {isHost && (
                <Button
                  onClick={() => submitAction("hint", {})}
                  variant="secondary"
                >
                  <Lightbulb className="h-4 w-4 mr-2" /> Request Hint
                </Button>
              )}
              <Button
                onClick={() => submitAction("check", {})}
                variant="primary"
              >
                <CheckCircle className="h-4 w-4 mr-2" /> Check Solution
              </Button>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <h3 className="font-semibold text-ink mb-3">
            Players ({players.length}/{session.max_players})
          </h3>
          <ul className="space-y-2">
            {players.map((player, index) => (
              <li key={player.player_id} className="flex items-center gap-2">
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
        </Card>
      </div>
    </div>
  );
}
