"use client";

import { Suspense } from "react";
import { usePathname } from "next/navigation";
import { GlobalCopilot } from "@/components/copilot/GlobalCopilot";
import { ProjectProvider } from "@/context/ProjectContext";

export function CopilotShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <ProjectProvider>
      {children}
      {pathname !== "/login" && <GlobalCopilot />}
    </ProjectProvider>
  );
}
