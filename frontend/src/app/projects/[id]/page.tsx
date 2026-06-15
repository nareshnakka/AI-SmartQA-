"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Play, Upload, Download, FileText, ChevronDown, ChevronRight,
  Loader2, Trash2, AlertTriangle, CheckCircle2,
} from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, MetricCard, Badge, Tabs } from "@/components/ui";
import { TestCaseFlowView, buildFlowSteps } from "@/components/flow/TestCaseFlowView";
import { apiFetch, apiUpload, exportUrl } from "@/lib/api";

interface Project {
  id: string;
  name: string;
  description: string | null;
  requirement_count: number;
  test_case_count: number;
  coverage_percentage: number;
}

interface Requirement {
  id: string;
  title: string;
  content: string;
  source_type: string;
  created_at: string;
}

interface TestCase {
  id: string;
  title: string;
  description: string;
  steps: string[];
  expected_results: string[];
  priority: string;
  tags: string[];
  status: string;
}

interface Coverage {
  coverage_percentage: number;
  total_requirements: number;
  covered_requirements: number;
  gaps: string[];
  risk_analysis?: { overall_risk_score?: string; high_risk_areas?: string[] };
}

interface GenerateResult {
  test_scenarios: string[];
  test_cases: TestCase[];
  coverage_matrix: Coverage;
  risk_analysis: Coverage["risk_analysis"];
}

export default function ProjectDetailPage() {
  const params = useParams();
  const projectId = params.id as string;
  const fileRef = useRef<HTMLInputElement>(null);

  const [project, setProject] = useState<Project | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [suites, setSuites] = useState<{ id: string; name: string; suite_type: string; test_case_ids: string[] }[]>([]);
  const [tab, setTab] = useState("generate");
  const [input, setInput] = useState("");
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [expandedCase, setExpandedCase] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const [p, reqs, cases, cov, suiteList] = await Promise.all([
      apiFetch<Project>(`/api/v1/projects/${projectId}`),
      apiFetch<Requirement[]>(`/api/v1/projects/${projectId}/requirements`),
      apiFetch<TestCase[]>(`/api/v1/projects/${projectId}/test-cases`),
      apiFetch<Coverage>(`/api/v1/projects/${projectId}/coverage`),
      apiFetch<{ id: string; name: string; suite_type: string; test_case_ids: string[] }[]>(
        `/api/v1/projects/${projectId}/test-suites`
      ).catch(() => []),
    ]);
    setProject(p);
    setRequirements(reqs);
    setTestCases(cases);
    setCoverage(cov);
    setSuites(suiteList);
  }, [projectId]);

  useEffect(() => { load().catch(() => setMessage("Failed to load project")); }, [load]);

  const generate = async () => {
    if (!input.trim()) return;
    setGenerating(true);
    setMessage("");
    try {
      const res = await apiFetch<GenerateResult>(`/api/v1/projects/${projectId}/generate`, {
        method: "POST",
        body: JSON.stringify({ content: input, source_type: "user_story", run_test_design: true }),
      });
      setResult(res);
      setMessage(`Generated ${res.test_cases.length} test cases`);
      await load();
      setTab("test-cases");
    } catch (e) {
      setMessage(String(e));
    } finally {
      setGenerating(false);
    }
  };

  const uploadFile = async (file: File) => {
    try {
      await apiUpload(`/api/v1/projects/${projectId}/requirements/upload`, file);
      setMessage(`Uploaded ${file.name}`);
      await load();
      setTab("requirements");
    } catch (e) {
      setMessage(String(e));
    }
  };

  const generateFromReq = async (reqId: string) => {
    setGenerating(true);
    try {
      const res = await apiFetch<GenerateResult>(
        `/api/v1/projects/${projectId}/generate/from-requirement/${reqId}`,
        { method: "POST" }
      );
      setResult(res);
      setMessage(`Generated ${res.test_cases.length} test cases`);
      await load();
      setTab("test-cases");
    } finally {
      setGenerating(false);
    }
  };

  const priorityVariant = (p: string) =>
    p === "high" ? "error" as const : p === "low" ? "neutral" as const : "warning" as const;

  if (!project) {
    return (
      <AppShell title="Project">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 animate-spin text-[var(--text-tertiary)]" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title={project.name}>
      <PageHeader
        title={project.name}
        subtitle={project.description || "AI test generation workspace"}
        breadcrumbs={[
          { label: "Projects", href: "/projects" },
          { label: project.name },
        ]}
        actions={
          <div className="flex gap-2">
            <Link href={`/studio?project=${projectId}`} className="ds-btn-secondary">
              QA Studio
            </Link>
            <a href={exportUrl(projectId, "csv")} className="ds-btn-secondary">
              <Download className="w-4 h-4" /> CSV
            </a>
            <a href={exportUrl(projectId, "json")} className="ds-btn-secondary">
              <Download className="w-4 h-4" /> JSON
            </a>
          </div>
        }
      />

      {/* Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricCard label="Requirements" value={project.requirement_count} />
        <MetricCard label="Test Cases" value={project.test_case_count} />
        <MetricCard
          label="Coverage"
          value={`${coverage?.coverage_percentage?.toFixed(0) ?? 0}%`}
          change={`${coverage?.covered_requirements ?? 0}/${coverage?.total_requirements ?? 0} covered`}
          changeType="positive"
        />
        <MetricCard
          label="Risk Level"
          value={coverage?.risk_analysis?.overall_risk_score ?? "—"}
          icon={<AlertTriangle className="w-4 h-4" />}
        />
      </div>

      {/* Coverage gaps */}
      {coverage && coverage.gaps.length > 0 && (
        <div className="ds-card mb-6 p-4 border-l-4 border-l-amber-500">
          <p className="text-xs font-semibold uppercase tracking-wider text-amber-700 mb-2">Coverage Gaps</p>
          <ul className="space-y-1">
            {coverage.gaps.map((g, i) => (
              <li key={i} className="text-sm text-[var(--text-secondary)] flex items-center gap-2">
                <span className="w-1 h-1 rounded-full bg-amber-500" />{g}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-4">
        <Tabs
          tabs={[
            { id: "generate", label: "Generate" },
            { id: "requirements", label: "Requirements", count: requirements.length },
            { id: "test-cases", label: "Test Cases", count: testCases.length },
            { id: "suites", label: "Test Suites", count: suites.length },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {/* Generate tab */}
      {tab === "generate" && (
        <div className="ds-card">
          <div className="ds-card-header">
            <div>
              <h2 className="text-sm font-semibold">Generate Test Cases</h2>
              <p className="text-xs text-[var(--text-tertiary)]">Paste requirements or upload a document</p>
            </div>
            <div className="flex gap-2">
              <input ref={fileRef} type="file" accept=".txt,.md,.csv,.json" className="hidden"
                onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0])} />
              <button onClick={() => fileRef.current?.click()} className="ds-btn-secondary">
                <Upload className="w-4 h-4" /> Upload
              </button>
              <button onClick={generate} disabled={generating || !input.trim()} className="ds-btn-primary">
                {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Generate
              </button>
            </div>
          </div>
          <div className="ds-card-body pt-0">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={12}
              className="ds-input font-mono text-xs leading-relaxed resize-none"
              placeholder={`As a [role], I want [action], so that [benefit].\n\nAcceptance Criteria:\n- ...`}
            />
          </div>
          {result && (
            <div className="px-6 pb-6">
              <div className="p-4 rounded-md bg-emerald-50 border border-emerald-200 flex items-center gap-2 text-sm text-emerald-800">
                <CheckCircle2 className="w-4 h-4" />
                Generated {result.test_scenarios.length} scenarios and {result.test_cases.length} test cases
              </div>
            </div>
          )}
        </div>
      )}

      {/* Requirements tab */}
      {tab === "requirements" && (
        <div className="ds-card">
          {requirements.length === 0 ? (
            <div className="p-12 text-center text-sm text-[var(--text-tertiary)]">
              No requirements yet. Use the Generate tab to add requirements.
            </div>
          ) : (
            <div className="divide-y divide-[var(--border-default)]">
              {requirements.map((req) => (
                <div key={req.id} className="px-6 py-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <FileText className="w-4 h-4 text-[var(--text-tertiary)]" />
                        <span className="text-sm font-medium">{req.title}</span>
                        <Badge variant="neutral">{req.source_type}</Badge>
                      </div>
                      <p className="text-xs text-[var(--text-secondary)] line-clamp-2">{req.content}</p>
                    </div>
                    <button
                      onClick={() => generateFromReq(req.id)}
                      disabled={generating}
                      className="ds-btn-secondary text-xs py-1.5 shrink-0"
                    >
                      <Play className="w-3 h-3" /> Regenerate
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Test cases tab */}
      {tab === "test-cases" && (
        <div className="space-y-2">
          {testCases.length === 0 ? (
            <div className="ds-card p-12 text-center text-sm text-[var(--text-tertiary)]">
              No test cases yet. Generate from requirements to create test cases.
            </div>
          ) : (
            testCases.map((tc) => (
              <div key={tc.id} className="ds-card">
                <button
                  className="w-full px-5 py-4 flex items-center gap-3 text-left"
                  onClick={() => setExpandedCase(expandedCase === tc.id ? null : tc.id)}
                >
                  {expandedCase === tc.id
                    ? <ChevronDown className="w-4 h-4 text-[var(--text-tertiary)]" />
                    : <ChevronRight className="w-4 h-4 text-[var(--text-tertiary)]" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{tc.title}</span>
                      <Badge variant={priorityVariant(tc.priority)}>{tc.priority}</Badge>
                      <Badge variant="neutral">{tc.status}</Badge>
                    </div>
                    <p className="text-xs text-[var(--text-tertiary)] mt-0.5 truncate">{tc.description}</p>
                  </div>
                  <span className="text-xs font-mono text-[var(--text-tertiary)]">{tc.steps.length} steps</span>
                </button>
                {expandedCase === tc.id && (
                  <div className="px-5 pb-5 border-t border-[var(--border-default)] pt-4 space-y-4">
                    <TestCaseFlowView
                      title={tc.title}
                      steps={buildFlowSteps(tc.steps, tc.expected_results)}
                      showHeader={false}
                    />
                    {tc.tags.length > 0 && (
                      <div className="flex gap-1 flex-wrap">
                        {tc.tags.map((t) => <Badge key={t} variant="info">{t}</Badge>)}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Suites tab */}
      {tab === "suites" && (
        <div className="ds-card">
          {suites.length === 0 ? (
            <div className="p-12 text-center text-sm text-[var(--text-tertiary)]">
              Test suites (regression/smoke packs) are created automatically during generation.
            </div>
          ) : (
            <table className="ds-table">
              <thead>
                <tr><th>Name</th><th>Type</th><th>Test Cases</th></tr>
              </thead>
              <tbody>
                {suites.map((s) => (
                  <tr key={s.id}>
                    <td className="font-medium text-[var(--text-primary)]">{s.name}</td>
                    <td><Badge variant="info">{s.suite_type}</Badge></td>
                    <td>{s.test_case_ids.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {message && (
        <p className="mt-4 text-sm p-3 rounded-md bg-[var(--surface-sunken)] text-[var(--text-secondary)]">{message}</p>
      )}
    </AppShell>
  );
}
