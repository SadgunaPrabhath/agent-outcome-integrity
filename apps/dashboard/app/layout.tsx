import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "AOIE — Agent Outcome Integrity Engine",
  description:
    "Independent verification of whether an AI agent actually achieved the state it claims.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="min-w-0 flex-1">
            <div className="mx-auto max-w-7xl px-6 py-6">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
