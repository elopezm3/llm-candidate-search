import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Candidate Search",
  description: "Ranks CVs against a job posting with embeddings + an LLM explanation.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
