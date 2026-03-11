import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "WarehouseIQ — LangGraph Agentic System",
  description: "5-agent LangGraph pipeline for Amazon FC operations intelligence",
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}