import type { Metadata } from "next";
import "./globals.css";
import "./refined.css";
import "./chat.css";

export const metadata: Metadata = {
  title: "모아 · 일정 허브",
  description: "대화에서 모은 일정, 사람별 간트와 크라임씬 모임",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="antialiased">{children}</body>
    </html>
  );
}
