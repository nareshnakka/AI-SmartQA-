import type { Metadata } from "next";
import "./globals.css";
import { CopilotShell } from "@/components/copilot/CopilotShell";

export const metadata: Metadata = {
  title: "QEOS — Quality Engineering Operating System",
  description: "Enterprise quality engineering platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <CopilotShell>{children}</CopilotShell>
      </body>
    </html>
  );
}
