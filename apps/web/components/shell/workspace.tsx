"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Icon, Modal } from "@/components/ui/primitives";
import { Ask } from "@/components/brief/ask";
import { DatasetList, Workflows } from "@/components/dataset/library";
import { DatasetWorkbench } from "@/components/dataset/workbench";
import { RunMonitor } from "@/components/workflow/run-monitor";
import { ReviewQueue } from "@/components/review/review-queue";
const navigation = [
  { path: "/ask", label: "Ask", icon: "ask" },
  { path: "/datasets", label: "Datasets", icon: "grid" },
  { path: "/runs", label: "Runs", icon: "runs" },
  { path: "/review", label: "Review queue", icon: "review" },
  { path: "/history", label: "History", icon: "history" },
];
export function Workspace() {
  const pathname = usePathname();
  const parts = pathname.split("/").filter(Boolean);
  const section = parts[0] || "ask";
  const [commands, setCommands] = useState(false);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        setCommands((value) => !value);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  let content: ReactNode;
  if (section === "ask") content = <Ask />;
  else if (section === "datasets")
    content = parts[1] ? (
      <DatasetWorkbench key={parts[1]} id={parts[1]} />
    ) : (
      <DatasetList />
    );
  else if (section === "runs" && parts[1])
    content = <RunMonitor id={parts[1]} key={parts[1]} />;
  else if (section === "runs" || section === "history")
    content = <Workflows history={section === "history"} />;
  else if (section === "review") content = <ReviewQueue />;
  else
    content = (
      <div className="empty">
        <h1>Page not found</h1>
        <Link href="/ask" className="button">
          Return to Ask
        </Link>
      </div>
    );
  return (
    <div className="workspace">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link className="brand" href="/ask" aria-label="ProofGrid home">
          <span className="brand-mark">
            <Icon name="grid" size={23} />
          </span>
          <span>
            ProofGrid<span className="brand-sub">EVIDENCE WORKSPACE</span>
          </span>
        </Link>
        <div className="workspace-label eyebrow">
          Research desk <span>01</span>
        </div>
        <nav aria-label="Main navigation">
          {navigation.map((item) => (
            <Link
              key={item.path}
              href={item.path}
              className={
                section === item.path.slice(1) ? "nav-link active" : "nav-link"
              }
              aria-current={section === item.path.slice(1) ? "page" : undefined}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {section === item.path.slice(1) && (
                <span className="nav-marker" />
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="ledger-stamp">
            Every value.
            <br />A traceable source.
          </div>
          <button className="command-button" onClick={() => setCommands(true)}>
            <Icon name="search" />
            <span>Go to…</span>
            <kbd>⌘ K</kbd>
          </button>
          <div className="workspace-user">
            <span className="user-initial">RD</span>
            <div>
              Research workspace<small>Code Cubicle 6.0</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span>/</span>
            <strong>
              {navigation.find((n) => n.path === "/" + section)?.label || "Ask"}
            </strong>
          </div>
          <div className="topbar-end">
            <span className="mono">PUBLIC / PERMITTED SOURCES</span>
            <button
              className="icon-button mobile-search"
              aria-label="Open navigation commands"
              onClick={() => setCommands(true)}
            >
              <Icon name="search" />
            </button>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          {content}
        </main>
        <footer className="workspace-footer">
          <span>
            ProofGrid <span className="footer-divider">/</span> Evidence is part
            of the dataset.
          </span>
          <span className="mono">CC 6.0</span>
        </footer>
      </div>
      {commands && (
        <Modal title="Go to workspace" onClose={() => setCommands(false)}>
          <div className="command-list">
            {navigation.map((item) => (
              <Link
                key={item.path}
                href={item.path}
                onClick={() => setCommands(false)}
              >
                <Icon name={item.icon} />
                {item.label}
                <span>↵</span>
              </Link>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
