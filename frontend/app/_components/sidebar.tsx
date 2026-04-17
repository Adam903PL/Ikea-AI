"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Sidebar() {
  const pathname = usePathname();
  const isActive = pathname.startsWith("/projects");

  return (
    <aside
      className="flex w-full flex-col justify-between px-5 py-6 lg:sticky lg:top-0 lg:h-screen lg:max-w-[260px]"
      style={{
        background: "var(--surface)",
        borderRight: "1px solid var(--border)",
        borderBottom: "none",
      }}
    >
      <div className="space-y-8">
        <div className="space-y-4">
          <div
            className="inline-flex items-center gap-2 rounded-md px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.2em]"
            style={{
              background: "var(--accent-dim)",
              border: "1px solid var(--accent-border)",
              color: "var(--accent)",
            }}
          >
            <span
              className="h-1.5 w-1.5 animate-pulse rounded-full"
              style={{ background: "var(--accent)" }}
            />
            IKEA 3D
          </div>

          <div>
            <h1
              className="text-[15px] font-bold leading-snug tracking-tight"
              style={{ color: "var(--foreground)" }}
            >
              Zarządzanie
              <br />
              projektami
            </h1>
            <p
              className="mt-1.5 font-mono text-[11px] font-light"
              style={{ color: "var(--foreground-subtle)" }}
            >
              {"// panel STEP viewer v2.1"}
            </p>
          </div>
        </div>

        <nav className="space-y-1">
          <p
            className="mb-2 px-2 font-mono text-[10px] uppercase tracking-[0.18em]"
            style={{ color: "var(--foreground-subtle)" }}
          >
            Nawigacja
          </p>
          <Link
            href="/projects"
            className="flex items-center justify-between rounded-md px-3 py-2.5 text-[13px] font-semibold transition-all"
            style={
              isActive
                ? {
                    background: "var(--accent-dim)",
                    border: "1px solid var(--accent-border)",
                    color: "var(--accent)",
                  }
                : {
                    background: "transparent",
                    border: "1px solid transparent",
                    color: "var(--foreground-muted)",
                  }
            }
            onMouseEnter={(e) => {
              if (!isActive) {
                (e.currentTarget as HTMLAnchorElement).style.background =
                  "var(--surface-2)";
                (e.currentTarget as HTMLAnchorElement).style.borderColor =
                  "var(--border)";
                (e.currentTarget as HTMLAnchorElement).style.color =
                  "var(--foreground)";
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                (e.currentTarget as HTMLAnchorElement).style.background =
                  "transparent";
                (e.currentTarget as HTMLAnchorElement).style.borderColor =
                  "transparent";
                (e.currentTarget as HTMLAnchorElement).style.color =
                  "var(--foreground-muted)";
              }
            }}
          >
            <span>Projekty</span>
            <span
              className="rounded px-1.5 py-0.5 font-mono text-[10px]"
              style={
                isActive
                  ? { background: "var(--accent-dim)", color: "var(--accent)" }
                  : {
                      background: "var(--surface-3)",
                      color: "var(--foreground-subtle)",
                    }
              }
            >
              01
            </span>
          </Link>
        </nav>
      </div>

      <div
        className="mt-8 rounded-lg p-3 lg:mt-0"
        style={{
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
        }}
      >
        <div
          className="flex items-center gap-2 text-[12px]"
          style={{ color: "var(--foreground-muted)" }}
        >
          <span
            className="h-2 w-2 rounded-full"
            style={{
              background: "var(--success)",
              boxShadow: "0 0 0 3px var(--success-dim)",
            }}
          />
          System online
        </div>
        <p
          className="mt-1.5 font-mono text-[11px]"
          style={{ color: "var(--success)" }}
        >
          {"// backend mesh pipeline ready"}
        </p>
      </div>
    </aside>
  );
}
