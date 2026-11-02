"use client";

import { useMemo } from "react";
import { Circle, User } from "lucide-react";
import { classNames } from "@/lib/utils";

interface PresenceIndicatorProps {
  userId: string;
  userName: string;
  userColor?: string;
  userAvatar?: string | null;
  status: "online" | "idle" | "away" | "offline";
  size?: "sm" | "md" | "lg";
  showName?: boolean;
  showTooltip?: boolean;
  className?: string;
}

const STATUS_CONFIG = {
  online: { color: "text-emerald-500", bg: "bg-emerald-500", label: "Online" },
  idle: { color: "text-amber-500", bg: "bg-amber-500", label: "Idle" },
  away: { color: "text-orange-500", bg: "bg-orange-500", label: "Away" },
  offline: { color: "text-faint", bg: "bg-faint", label: "Offline" },
};

const SIZE_CONFIG = {
  sm: {
    indicator: "h-2 w-2",
    avatar: "h-6 w-6",
    name: "text-xs",
    icon: "h-3 w-3",
  },
  md: {
    indicator: "h-2.5 w-2.5",
    avatar: "h-8 w-8",
    name: "text-sm",
    icon: "h-4 w-4",
  },
  lg: {
    indicator: "h-3 w-3",
    avatar: "h-10 w-10",
    name: "text-base",
    icon: "h-5 w-5",
  },
};

export function PresenceIndicator({
  userId,
  userName,
  userColor,
  userAvatar,
  status,
  size = "md",
  showName = false,
  showTooltip = true,
  className,
}: PresenceIndicatorProps) {
  const config = useMemo(() => STATUS_CONFIG[status], [status]);
  const sizes = useMemo(() => SIZE_CONFIG[size], [size]);

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
    // Generate consistent color from userId
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
    for (let i = 0; i < userId.length; i++) {
      hash = (hash * 31 + userId.charCodeAt(i)) >>> 0;
    }
    return colors[hash % colors.length];
  }, [userId, userColor]);

  const statusDot = (
    <span
      className={classNames(
        "relative flex-shrink-0 rounded-full border-2 border-canvas",
        config.bg,
        sizes.indicator,
      )}
      aria-label={`${config.label} status for ${userName}`}
    />
  );

  const avatar = userAvatar ? (
    <img
      src={userAvatar}
      alt={userName}
      className={classNames("rounded-full object-cover", sizes.avatar)}
    />
  ) : (
    <div
      className={classNames(
        "rounded-full flex items-center justify-center font-medium text-white",
        sizes.avatar,
      )}
      style={{ backgroundColor: avatarBgColor }}
    >
      {initials}
    </div>
  );

  if (showName) {
    return (
      <div className={classNames("flex items-center gap-2", className)}>
        <div className="relative">
          {avatar}
          {statusDot}
        </div>
        <span className={classNames("truncate font-medium", sizes.name)}>
          {userName}
        </span>
      </div>
    );
  }

  const content = (
    <div className={classNames("relative inline-flex", className)}>
      {avatar}
      {statusDot}
    </div>
  );

  if (!showTooltip) return content;

  // Simple tooltip using title attribute for now
  // In production, use a proper tooltip component
  return (
    <div
      className="relative inline-flex"
      title={`${userName} - ${config.label}`}
    >
      {content}
    </div>
  );
}

export function PresenceBadge({
  userId,
  userName,
  userColor,
  userAvatar,
  status,
  size = "sm",
  className,
}: Omit<PresenceIndicatorProps, "showName" | "showTooltip">) {
  return (
    <PresenceIndicator
      userId={userId}
      userName={userName}
      userColor={userColor}
      userAvatar={userAvatar}
      status={status}
      size={size}
      showName={true}
      showTooltip={true}
      className={className}
    />
  );
}

export function OnlineUsersList({
  users,
  maxVisible = 5,
  size = "sm",
  className,
}: {
  users: Array<{
    userId: string;
    userName: string;
    userColor?: string;
    userAvatar?: string | null;
    status: "online" | "idle" | "away" | "offline";
  }>;
  maxVisible?: number;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const onlineUsers = useMemo(
    () => users.filter((u) => u.status === "online"),
    [users],
  );

  const visibleUsers = onlineUsers.slice(0, maxVisible);
  const remainingCount = onlineUsers.length - maxVisible;

  return (
    <div className={classNames("flex items-center -space-x-2", className)}>
      {visibleUsers.map((user) => (
        <PresenceIndicator
          key={user.userId}
          userId={user.userId}
          userName={user.userName}
          userColor={user.userColor}
          userAvatar={user.userAvatar}
          status={user.status}
          size={size}
          showTooltip={true}
        />
      ))}
      {remainingCount > 0 && (
        <div
          className={classNames(
            "flex items-center justify-center rounded-full border-2 border-canvas bg-muted text-muted font-medium",
            SIZE_CONFIG[size].avatar,
          )}
        >
          +{remainingCount}
        </div>
      )}
    </div>
  );
}
