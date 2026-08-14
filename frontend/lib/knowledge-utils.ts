export type Tone = "neutral" | "brand" | "success" | "warning" | "danger";

export function severityTone(severity?: string | null): Tone {
  switch (severity) {
    case "critical":
      return "danger";
    case "high":
      return "danger";
    case "medium":
      return "warning";
    case "low":
      return "success";
    case "info":
      return "brand";
    default:
      return "neutral";
  }
}

export function confidenceTone(confidence: number | null | undefined): Tone {
  if (confidence === null || confidence === undefined) return "neutral";
  if (confidence >= 0.7) return "success";
  if (confidence >= 0.4) return "brand";
  return "warning";
}

const KIND_LABELS: Record<string, string> = {
  contradiction: "Contradiction",
  change: "Change",
  risk: "Emerging risk",
  gap: "Knowledge gap",
  decision_required: "Decision required",
  impact: "Impact",
  opportunity: "Opportunity",
  trend: "Trend",
  verification_required: "Verification required",
  recommendation: "Recommendation",
  anomaly: "Anomaly",
  dependency: "Dependency",
};

export function kindLabel(kind?: string | null): string {
  if (!kind) return "Unknown";
  return KIND_LABELS[kind] ?? kind.replace(/_/g, " ");
}

const LIFECYCLE_LABELS: Record<string, string> = {
  detected: "Detected",
  candidate: "Candidate",
  reviewed: "Reviewed",
  accepted: "Accepted",
  rejected: "Rejected",
  converted: "Converted",
  executed: "Executed",
  verified: "Verified",
};

export function lifecycleLabel(lifecycle: string): string {
  return LIFECYCLE_LABELS[lifecycle] ?? lifecycle.replace(/_/g, " ");
}

export function lifecycleTone(lifecycle: string): Tone {
  switch (lifecycle) {
    case "detected":
      return "brand";
    case "candidate":
      return "brand";
    case "reviewed":
      return "neutral";
    case "accepted":
      return "success";
    case "rejected":
      return "danger";
    case "converted":
      return "warning";
    case "executed":
      return "success";
    case "verified":
      return "success";
    default:
      return "neutral";
  }
}

export function authorityLabel(level: number | null | undefined): string {
  if (level === null || level === undefined) return "unverified";
  if (level >= 5) return "authoritative";
  if (level === 4) return "strong";
  if (level === 3) return "moderate";
  if (level === 2) return "weak";
  return "unverified";
}
