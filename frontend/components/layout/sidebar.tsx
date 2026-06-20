"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  Newspaper,
  Rss,
  Star,
  Settings,
  User,
  ChevronsUpDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { HealthPill } from "./health-pill";
import { ThemeToggle } from "./theme-toggle";
import { LanguageToggle } from "./language-toggle";
import { Separator } from "@/components/ui/separator";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: "Overview",
    items: [
      { label: "Dashboard", href: "/", icon: LayoutDashboard },
      { label: "Digests", href: "/digests", icon: FileText },
      { label: "News", href: "/news", icon: Newspaper },
    ],
  },
  {
    title: "Configure",
    items: [
      { label: "Sources", href: "/sources", icon: Rss },
      { label: "Watchlist", href: "/watchlist", icon: Star },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

function SignalMark({ className }: { className?: string }) {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      {/* Signal pulse glyph — concentric arcs suggesting a live signal */}
      <rect x="12" y="18" width="4" height="6" rx="2" fill="currentColor" />
      <path
        d="M8 16a7 7 0 0 1 12 0"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
        opacity="0.7"
      />
      <path
        d="M4 13a12 12 0 0 1 20 0"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
        opacity="0.4"
      />
    </svg>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <aside className="flex h-full w-64 flex-col border-r border-border bg-sidebar">
      {/* Brand lockup */}
      <div className="flex items-center gap-3 px-4 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <SignalMark className="h-5 w-5" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold tracking-tight text-sidebar-foreground">
            Catch-Up
          </span>
          <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
            Console
          </span>
        </div>
      </div>

      {/* Workspace indicator — presentational, no switcher wired up yet */}
      <div className="px-3 pb-3">
        <div className="flex w-full items-center justify-between rounded-lg border border-border bg-muted/40 px-3 py-2 text-left">
          <span className="text-xs font-medium text-foreground">
            Default workspace
          </span>
          <ChevronsUpDown
            className="h-3.5 w-3.5 text-muted-foreground"
            aria-hidden="true"
          />
        </div>
      </div>

      <Separator className="mx-3 w-auto" />

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-3" aria-label="Main navigation">
        {NAV_GROUPS.map((group) => (
          <div key={group.title} className="mb-4">
            <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              {group.title}
            </p>
            <ul className="space-y-0.5" role="list">
              {group.items.map((item) => {
                const active = isActive(item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        "group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        active
                          ? "bg-sidebar-accent text-sidebar-accent-foreground"
                          : "text-sidebar-foreground/70 hover:bg-muted hover:text-sidebar-foreground"
                      )}
                      aria-current={active ? "page" : undefined}
                    >
                      {/* Active indicator — emerald left accent */}
                      {active && (
                        <span
                          className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-primary"
                          aria-hidden="true"
                        />
                      )}
                      <Icon
                        className={cn(
                          "h-4 w-4 shrink-0 transition-colors",
                          active
                            ? "text-primary"
                            : "text-muted-foreground group-hover:text-sidebar-foreground"
                        )}
                        aria-hidden="true"
                      />
                      <span>{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <Separator className="mx-3 w-auto" />

      {/* Footer */}
      <div className="px-3 py-3 space-y-2">
        {/* Health + Theme row */}
        <div className="flex items-center justify-between px-1">
          <HealthPill />
          <div className="flex items-center gap-1.5">
            <LanguageToggle />
            <ThemeToggle />
          </div>
        </div>

        {/* Profile row — presentational, no account menu wired up yet */}
        <div className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-muted">
            <User className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          </div>
          <span className="text-xs font-medium text-muted-foreground">
            Default user
          </span>
        </div>
      </div>
    </aside>
  );
}
