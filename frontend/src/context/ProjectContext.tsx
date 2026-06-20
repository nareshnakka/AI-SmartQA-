"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
  Suspense,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { fetchProjects, type ProjectListItem } from "@/lib/projects";
import { getStoredProjectId, setStoredProjectId } from "@/lib/active-project";

export type ActiveProject = ProjectListItem;

interface ProjectContextValue {
  projectId: string;
  setProjectId: (id: string) => void;
  projects: ActiveProject[];
  activeProject: ActiveProject | null;
  loading: boolean;
  ready: boolean;
}

const defaultValue: ProjectContextValue = {
  projectId: "",
  setProjectId: () => {},
  projects: [],
  activeProject: null,
  loading: true,
  ready: false,
};

const ProjectContext = createContext<ProjectContextValue>(defaultValue);

function ProjectProviderInner({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [projects, setProjects] = useState<ActiveProject[]>([]);
  const [projectId, setProjectIdState] = useState("");
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchProjects()
      .then((list) => {
        if (cancelled) return;
        setProjects(list);
        const fromUrl = searchParams.get("project");
        const fromStorage = getStoredProjectId();
        let id = "";
        if (fromUrl && list.some((p) => p.id === fromUrl)) id = fromUrl;
        else if (fromStorage && list.some((p) => p.id === fromStorage)) id = fromStorage;
        else if (list[0]) id = list[0].id;
        setProjectIdState(id);
        if (id) setStoredProjectId(id);
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) setReady(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const fromUrl = searchParams.get("project");
    if (!fromUrl || !projects.length) return;
    if (projects.some((p) => p.id === fromUrl)) {
      setProjectIdState((prev) => (prev === fromUrl ? prev : fromUrl));
      setStoredProjectId(fromUrl);
    }
  }, [searchParams, projects]);

  const setProjectId = useCallback(
    (id: string) => {
      setProjectIdState(id);
      setStoredProjectId(id || null);
      if (pathname === "/login") return;
      const params = new URLSearchParams(searchParams.toString());
      if (id) params.set("project", id);
      else params.delete("project");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  const activeProject = useMemo(
    () => projects.find((p) => p.id === projectId) ?? null,
    [projects, projectId]
  );

  const value = useMemo(
    () => ({ projectId, setProjectId, projects, activeProject, loading, ready }),
    [projectId, setProjectId, projects, activeProject, loading, ready]
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<ProjectContext.Provider value={defaultValue}>{children}</ProjectContext.Provider>}>
      <ProjectProviderInner>{children}</ProjectProviderInner>
    </Suspense>
  );
}

export function useActiveProject() {
  return useContext(ProjectContext);
}
