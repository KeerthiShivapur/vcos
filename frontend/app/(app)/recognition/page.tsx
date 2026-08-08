"use client";

import { Suspense, useEffect, useState } from "react";
import { Award, Heart, Plus, Trophy } from "lucide-react";

import {
  getAllBadges,
  getMyBadges,
  getRecognitionLeaderboard,
  getRecognitionStats,
  giveRecognition,
  listEmployees,
  listRecognition,
} from "@/lib/api";
import type { Badge, EmployeeBadge, EmployeeSummary, Recognition } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Badge as Pill } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { timeAgo, titleCase } from "@/lib/utils";

const CATEGORIES = ["teamwork", "leadership", "innovation", "delivery", "customer_focus", "mentorship", "culture", "excellence"];

export default function RecognitionPage() {
  return (
    <Suspense fallback={null}>
      <RecognitionContent />
    </Suspense>
  );
}

function RecognitionContent() {
  const { user } = useAuth();
  const [recognitions, setRecognitions] = useState<Recognition[]>([]);
  const [stats, setStats] = useState<{ total: number; this_month: number; categories: { category: string; count: number }[] } | null>(null);
  const [leaderboard, setLeaderboard] = useState<{ employee_id: string; badge_count: number; employee_name: string }[]>([]);
  const [myBadges, setMyBadges] = useState<EmployeeBadge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [giveOpen, setGiveOpen] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [list, statsData, board, badges] = await Promise.all([
        listRecognition({ limit: 100 }),
        getRecognitionStats(),
        getRecognitionLeaderboard(10),
        getMyBadges(),
      ]);
      setRecognitions(list);
      setStats(statsData);
      setLeaderboard(board);
      setMyBadges(badges);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load recognition");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Recognition"
        description="Celebrate the people who make great work happen."
        actions={
          <Button size="sm" onClick={() => setGiveOpen(true)}>
            <Plus className="h-4 w-4" /> Give recognition
          </Button>
        }
      />

      {error ? (
        <ErrorState title="Could not load recognition" message={error} onRetry={load} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading recognition" /></div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-line bg-surface p-4">
              <p className="text-[12px] text-faint">All time</p>
              <p className="mt-1 text-2xl font-bold text-ink">{stats?.total ?? 0}</p>
            </div>
            <div className="rounded-lg border border-line bg-surface p-4">
              <p className="text-[12px] text-faint">This month</p>
              <p className="mt-1 text-2xl font-bold text-brand">{stats?.this_month ?? 0}</p>
            </div>
            <div className="rounded-lg border border-line bg-surface p-4">
              <p className="text-[12px] text-faint">Your badges</p>
              <p className="mt-1 text-2xl font-bold text-ink">{myBadges.length}</p>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-3 lg:col-span-2">
              <h3 className="text-sm font-semibold text-ink">Recent recognition</h3>
              {recognitions.length === 0 ? (
                <EmptyState
                  icon={Heart}
                  title="No recognition yet"
                  description="Recognize a teammate for their contribution."
                  action={<Button size="sm" onClick={() => setGiveOpen(true)}><Plus className="h-4 w-4" /> Give recognition</Button>}
                />
              ) : (
                recognitions.map((recognition) => (
                  <div key={recognition.id} className="rounded-lg border border-line bg-surface p-4">
                    <div className="flex items-center gap-2">
                      <Avatar name={recognition.giver_name} size="sm" />
                      <p className="text-[13px] text-muted">
                        <span className="font-semibold text-ink">{recognition.giver_name}</span> recognized{" "}
                        <span className="font-semibold text-ink">{recognition.recipient_name}</span>
                      </p>
                      <span className="ml-auto text-[12px] text-faint">{timeAgo(recognition.created_at)}</span>
                    </div>
                    {recognition.message && (
                      <p className="mt-2 text-[13px] text-muted">“{recognition.message}”</p>
                    )}
                    <div className="mt-2 flex gap-1.5">
                      <Pill tone="brand">{titleCase(recognition.category)}</Pill>
                      {recognition.badge_code && <Pill tone="warning">🏅 {titleCase(recognition.badge_code)}</Pill>}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="space-y-6">
              <div className="rounded-lg border border-line bg-surface p-4">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                  <Trophy className="h-4 w-4 text-brand" /> Badge leaderboard
                </h3>
                {leaderboard.length === 0 ? (
                  <p className="mt-2 text-[13px] text-faint">No badges awarded yet.</p>
                ) : (
                  <ul className="mt-3 space-y-2">
                    {leaderboard.map((entry, index) => (
                      <li key={entry.employee_id} className="flex items-center gap-2 text-[13px]">
                        <span className="w-5 text-[12px] font-bold text-faint">#{index + 1}</span>
                        <span className="flex-1 truncate font-medium text-ink">{entry.employee_name}</span>
                        <span className="text-[12px] text-muted">{entry.badge_count} badges</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="rounded-lg border border-line bg-surface p-4">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                  <Award className="h-4 w-4 text-brand" /> My badges
                </h3>
                {myBadges.length === 0 ? (
                  <p className="mt-2 text-[13px] text-faint">You haven't received any badges yet.</p>
                ) : (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {myBadges.map((badge) => (
                      <div
                        key={badge.id}
                        title={badge.badge_name}
                        className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft/60 text-xl"
                      >
                        {badge.badge_icon}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      <GiveRecognitionModal
        open={giveOpen}
        onClose={() => setGiveOpen(false)}
        onGiven={async (payload) => {
          await giveRecognition(payload);
          setGiveOpen(false);
          load();
        }}
      />
    </div>
  );
}

function GiveRecognitionModal({
  open,
  onClose,
  onGiven,
}: {
  open: boolean;
  onClose: () => void;
  onGiven: (payload: { recipient_id: string; category: string; message?: string; badge_code?: string }) => Promise<void>;
}) {
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [badges, setBadges] = useState<Badge[]>([]);
  const [recipientId, setRecipientId] = useState("");
  const [category, setCategory] = useState("teamwork");
  const [message, setMessage] = useState("");
  const [badgeCode, setBadgeCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    listEmployees({ page_size: 200 })
      .then(setEmployees)
      .catch(() => undefined);
    getAllBadges()
      .then(setBadges)
      .catch(() => undefined);
  }, [open]);

  async function submit() {
    if (!recipientId) {
      setError("Pick a recipient");
      return;
    }
    setError(null);
    try {
      await onGiven({
        recipient_id: recipientId,
        category,
        message: message.trim() || undefined,
        badge_code: badgeCode || undefined,
      });
      setRecipientId("");
      setMessage("");
      setBadgeCode("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to give recognition");
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Give recognition"
      description="Recognize a teammate's contribution."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit}>Give</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Select
          label="Recipient"
          value={recipientId}
          onChange={(e) => setRecipientId(e.target.value)}
          placeholder="Select a colleague"
          options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
        />
        <Select
          label="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          options={CATEGORIES.map((c) => ({ value: c, label: titleCase(c) }))}
        />
        {badges.length > 0 && (
          <Select
            label="Badge (optional)"
            value={badgeCode}
            onChange={(e) => setBadgeCode(e.target.value)}
            placeholder="No badge"
            options={badges.map((b) => ({ value: b.code, label: `${b.icon} ${b.name}` }))}
          />
        )}
        <Textarea label="Message" placeholder="Why are you recognizing them?" value={message} onChange={(e) => setMessage(e.target.value)} rows={3} />
        {error && <p className="text-[13px] text-danger">{error}</p>}
      </div>
    </Modal>
  );
}
