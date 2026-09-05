import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import {PRIMARY_NAVIGATION} from "../lib/ui-labels";

export const metadata: Metadata = {
  title: "Character Studio | Game AI Agent",
  description: "A developer workbench for grounded character generation.",
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="app-frame">
          <aside className="app-sidebar" aria-label="Primary navigation">
            <div className="sidebar-brand">GA / STUDIO</div>
            <p className="sidebar-label">工作区</p>
            <nav className="sidebar-nav">
              {PRIMARY_NAVIGATION.map((item) => <Link href={item.href} key={item.href}>{item.label}</Link>)}
            </nav>
            <p className="sidebar-note">Web v0.1<br />只读资料视图</p>
          </aside>
          <div className="app-main">{children}</div>
        </div>
      </body>
    </html>
  );
}
