import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Character Studio | Game AI Agent",
  description: "A developer workbench for grounded character generation.",
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return (
    <html lang="en">
      <body>
        <div className="app-frame">
          <aside className="app-sidebar" aria-label="Primary navigation">
            <div className="sidebar-brand">GA / Studio</div>
            <p className="sidebar-label">Workspace</p>
            <nav className="sidebar-nav">
              <Link href="/studio">Character Studio</Link>
              <Link href="/saved-characters">Saved Characters</Link>
              <Link href="/canon">Canon</Link>
              <Link href="/characters">Characters</Link>
              <Link href="/skills">Skill Playground</Link>
            </nav>
            <p className="sidebar-note">Web v0.1<br />Read-only corpus views</p>
          </aside>
          <div className="app-main">{children}</div>
        </div>
      </body>
    </html>
  );
}
