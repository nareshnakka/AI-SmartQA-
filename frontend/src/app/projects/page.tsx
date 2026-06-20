"use client";

import { useState } from "react";
import Link from "next/link";
import { Plus, FolderKanban, ArrowRight, AlertCircle, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, EmptyState } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { invalidateProjectsCache } from "@/lib/projects";
import { useProjects } from "@/components/ProjectSelector";

interface Project {
  id: string;
  name: string;
  description: string | null;
  requirement_count: number;
  test_case_count: number;
  created_at: string;
}

export default function ProjectsPage() {
  const { projects, loading, error, reload } = useProjects();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const createProject = async () => {
    if (!name.trim()) return;
    setCreating(true);
    try {
      const project = await apiFetch<Project>("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify({ name, description: description || null }),
      });
      invalidateProjectsCache();
      setName("");
      setDescription("");
      setShowCreate(false);
      window.location.href = `/projects/${project.id}`;
    } finally {
      setCreating(false);
    }
  };

  return (
    <AppShell title="Projects">
      <PageHeader
        title="Projects"
        subtitle="Organize requirements, test cases, and coverage by project"
        breadcrumbs={[{ label: "Overview" }, { label: "Projects" }]}
        actions={
          <button onClick={() => setShowCreate(true)} className="ds-btn-primary">
            <Plus className="w-4 h-4" />
            New Project
          </button>
        }
      />

      {showCreate && (
        <div className="ds-card mb-6">
          <div className="ds-card-header">
            <h2 className="text-sm font-semibold">Create Project</h2>
          </div>
          <div className="ds-card-body space-y-4 max-w-lg">
            <div>
              <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">Project Name</label>
              <input className="ds-input" value={name} onChange={(e) => setName(e.target.value)}
                placeholder="e.g. E-Commerce Platform QA" />
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">Description</label>
              <textarea className="ds-input resize-none" rows={3} value={description}
                onChange={(e) => setDescription(e.target.value)} placeholder="Project scope and context" />
            </div>
            <div className="flex gap-2">
              <button onClick={createProject} disabled={creating} className="ds-btn-primary">Create & Open</button>
              <button onClick={() => setShowCreate(false)} className="ds-btn-secondary">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="ds-card p-8 text-center text-sm text-[var(--text-tertiary)]">Loading projects…</div>
      ) : error ? (
        <div className="ds-card">
          <EmptyState
            icon={<AlertCircle className="w-6 h-6 text-red-500" />}
            title="Could not load projects"
            description={`${error}. Make sure the QEOS backend is running on port 8000.`}
            action={
              <button onClick={reload} className="ds-btn-primary">
                <RefreshCw className="w-4 h-4" /> Retry
              </button>
            }
          />
        </div>
      ) : projects.length === 0 ? (
        <div className="ds-card">
          <EmptyState
            icon={<FolderKanban className="w-6 h-6" />}
            title="No projects yet"
            description="Create a project to start generating test cases from requirements."
            action={
              <button onClick={() => setShowCreate(true)} className="ds-btn-primary">
                <Plus className="w-4 h-4" /> Create Project
              </button>
            }
          />
        </div>
      ) : (
        <div className="ds-card">
          <table className="ds-table">
            <thead>
              <tr>
                <th>Project</th>
                <th>Requirements</th>
                <th>Test Cases</th>
                <th>Created</th>
                <th className="w-24"></th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.id}>
                  <td>
                    <Link href={`/projects/${project.id}`} className="flex items-center gap-2.5 group">
                      <div className="w-8 h-8 rounded-md bg-brand-50 flex items-center justify-center">
                        <FolderKanban className="w-4 h-4 text-brand-700" />
                      </div>
                      <div>
                        <span className="font-medium text-[var(--text-primary)] group-hover:text-brand-700 transition-colors">
                          {project.name}
                        </span>
                        {project.description && (
                          <p className="text-xs text-[var(--text-tertiary)] truncate max-w-xs">{project.description}</p>
                        )}
                      </div>
                    </Link>
                  </td>
                  <td><Badge variant="neutral">{project.requirement_count ?? 0}</Badge></td>
                  <td><Badge variant="info">{project.test_case_count ?? 0}</Badge></td>
                  <td className="font-mono text-xs">
                    {project.created_at ? new Date(project.created_at).toLocaleDateString() : "—"}
                  </td>
                  <td>
                    <Link href={`/projects/${project.id}`} className="ds-btn-ghost text-xs py-1 px-2">
                      Open <ArrowRight className="w-3 h-3" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AppShell>
  );
}
