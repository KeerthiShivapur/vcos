"use client";

import { MeetingRoom } from "@/components/meetings/MeetingRoom";
import { useAuth } from "@/hooks/useAuth";

interface MeetingRoomPageProps {
  params: {
    meetingId: string;
  };
}

export default function MeetingRoomPage({ params }: MeetingRoomPageProps) {
  const { loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand border-t-transparent mx-auto mb-4" />
          <p className="text-muted">Loading meeting...</p>
        </div>
      </div>
    );
  }

  return <MeetingRoom meetingId={params.meetingId} />;
}
