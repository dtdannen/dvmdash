// app/dvm-stats/layout.tsx
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DVMDash Stats",
};

export default function DVMStatsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
