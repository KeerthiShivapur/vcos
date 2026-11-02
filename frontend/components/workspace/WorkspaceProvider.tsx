"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import type { CompanyExperienceProfile } from "@/types";
import {
  getVisibleWorkspaces,
  type WorkspaceDefinition,
} from "./WorkspaceRegistry";

interface WorkspaceContextType {
  currentWorkspace: WorkspaceDefinition | null;
  availableWorkspaces: WorkspaceDefinition[];
  setCurrentWorkspace: (workspaceId: string) => void;
  isLoading: boolean;
  profile: CompanyExperienceProfile | null;
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(
  undefined,
);

interface WorkspaceProviderProps {
  children: ReactNode;
  initialProfile?: CompanyExperienceProfile;
}

export function WorkspaceProvider({
  children,
  initialProfile = "startup",
}: WorkspaceProviderProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [profile, setProfile] = useState<CompanyExperienceProfile | null>(
    initialProfile,
  );
  const [availableWorkspaces, setAvailableWorkspaces] = useState<
    WorkspaceDefinition[]
  >([]);
  const [currentWorkspace, setCurrentWorkspaceState] =
    useState<WorkspaceDefinition | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load available workspaces based on profile
  useEffect(() => {
    const workspaces = getVisibleWorkspaces(profile || "startup");
    setAvailableWorkspaces(workspaces);

    // Set initial workspace based on pathname
    const current = workspaces.find((w) =>
      pathname.startsWith(w.defaultRoute || w.routes[0]),
    );
    if (current) {
      setCurrentWorkspaceState(current);
    } else if (workspaces.length > 0) {
      setCurrentWorkspaceState(workspaces[0]);
    }
    setIsLoading(false);
  }, [profile, pathname]);

  const setCurrentWorkspace = useCallback(
    (workspaceId: string) => {
      const workspace = availableWorkspaces.find((w) => w.id === workspaceId);
      if (workspace) {
        setCurrentWorkspaceState(workspace);
        router.push(workspace.defaultRoute || workspace.routes[0]);
      }
    },
    [availableWorkspaces, router],
  );

  return (
    <WorkspaceContext.Provider
      value={{
        currentWorkspace,
        availableWorkspaces,
        setCurrentWorkspace,
        isLoading,
        profile,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
