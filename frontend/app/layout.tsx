import type { Metadata } from "next";
import Link from "next/link";
import { StoreProvider } from "@/lib/store";
import "./globals.css";

export const metadata: Metadata = {
  title: "SchoolSync AI",
  description: "Extract school calendar PDFs into reviewed, duplicate-safe calendar events.",
};

const NAV = [
  { href: "/", label: "Import" },
  { href: "/review", label: "Review" },
  { href: "/connect", label: "Connect" },
  { href: "/sync", label: "Export & sync" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <StoreProvider>
          <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:p-2">
            Skip to content
          </a>
          <header className="border-b border-line bg-surface">
            <nav aria-label="Primary" className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
              <span className="font-semibold">SchoolSync AI</span>
              <ul className="flex gap-4 text-sm">
                {NAV.map((n) => (
                  <li key={n.href}>
                    <Link className="text-muted hover:text-ink" href={n.href}>
                      {n.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </header>
          <main id="main" className="mx-auto max-w-7xl px-4 py-6">
            {children}
          </main>
        </StoreProvider>
      </body>
    </html>
  );
}
