"use client";

import { useState } from "react";
import Link from "next/link";
import { Search, LayoutGrid, Settings, Users, FileText, Calendar, Zap } from "lucide-react";

import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { useAuth } from "@/hooks/useAuth";

export default function AdaptiveWorkspacePage() {
  const { user } = useAuth();

  return (
    <div className="max-w-7xl mx-auto space-y-6 p-4">
      <PageHeader
        title="Workspace"
        description="Your adaptive company operating surface."
        actions={
          <Link href="/search">
            <Button variant="secondary">
              <Search className="h-4 w-4 mr-2" /> Search
            </Button>
          </Link>
        }
      />

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="grid w-full grid-cols-4 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger value="overview" className="py-2 flex items-center gap-2">
            <LayoutGrid className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="team" className="py-2 flex items-center gap-2">
            <Users className="h-4 w-4" />
            Team
          </TabsTrigger>
          <TabsTrigger value="tasks" className="py-2 flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Tasks
          </TabsTrigger>
          <TabsTrigger value="calendar" className="py-2 flex items-center gap-2">
            <Calendar className="h-4 w-4" />
            Calendar
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Active Objectives" value="3" icon={Zap} />
            <StatCard label="Open Tasks" value="12" icon={FileText} />
            <StatCard label="Upcoming Meetings" value="5" icon={Calendar} />
            <StatCard label="Team Members" value="8" icon={Users} />
          </div>

          <Card>
            <div className="p-5 text-center">
              <p className="text-muted mb-4">Your adaptive workspace is ready. Connect your tools and invite your team to get started.</p>
              <div className="flex gap-2 justify-center">
                <Button variant="secondary" onClick={() => window.location.href = "/settings?tab=integrations"}>
                  <Zap className="h-4 w-4 mr-2" /> Connect Integrations
                </Button>
                <Button onClick={() => window.location.href = "/settings?tab=members"}>
                  <Users className="h-4 w-4 mr-2" /> Invite Team
                </Button>
              </div>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="team" className="space-y-6">
          <Card>
            <div className="p-5 text-center">
              <Users className="h-12 w-12 text-muted mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-ink mb-2">Team Workspace</h3>
              <p className="text-muted mb-4">Manage team members, roles, and permissions.</p>
              <Button onClick={() => window.location.href = "/settings?tab=members"}>
                <Link href="/settings?tab=members">Manage Team</Link>
              </Button>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="tasks" className="space-y-6">
          <Card>
            <div className="p-5 text-center">
              <FileText className="h-12 w-12 text-muted mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-ink mb-2">Tasks & Projects</h3>
              <p className="text-muted mb-4">Track tasks, projects, and progress.</p>
              <Button onClick={() => window.location.href = "/settings?tab=members"}>
                <Link href="/tasks">View Tasks</Link>
              </Button>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="calendar" className="space-y-6">
          <Card>
            <div className="p-5 text-center">
              <Calendar className="h-12 w-12 text-muted mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-ink mb-2">Calendar & Meetings</h3>
              <p className="text-muted mb-4">Schedule and manage meetings.</p>
              <Button onClick={() => window.location.href = "/settings?tab=members"}>
                <Link href="/meetings">View Meetings</Link>
              </Button>
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}