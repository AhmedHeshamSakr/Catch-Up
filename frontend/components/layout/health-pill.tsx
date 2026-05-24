"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type Status = "online" | "offline" | "checking";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function HealthPill() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let mounted = true;
    let controller: AbortController | null = null;

    const check = () => {
      controller?.abort();
      controller = new AbortController();
      const ctrl = controller;
      const timer = setTimeout(() => ctrl.abort(), 5000);
      fetch(`${API_BASE}/api/health`, { signal: ctrl.signal })
        .then((res) => {
          clearTimeout(timer);
          if (mounted) setStatus(res.ok ? "online" : "offline");
        })
        .catch(() => {
          clearTimeout(timer);
          if (mounted) setStatus("offline");
        });
    };

    check();
    const interval = setInterval(check, 20_000);
    return () => {
      mounted = false;
      controller?.abort();
      clearInterval(interval);
    };
  }, []);

  return (
    <div
      className="flex items-center gap-1.5"
      role="status"
      aria-label={`API status: ${status}`}
      title={`API status: ${status}`}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full transition-colors",
          status === "online" && "bg-primary animate-pulse",
          status === "offline" && "bg-muted-foreground",
          status === "checking" && "bg-muted-foreground/50 animate-pulse"
        )}
        aria-hidden="true"
      />
      <span
        className={cn(
          "font-mono text-[10px] font-medium tabular-nums",
          status === "online" ? "text-primary" : "text-muted-foreground"
        )}
      >
        {status === "online"
          ? "API online"
          : status === "offline"
          ? "API offline"
          : "Checking…"}
      </span>
    </div>
  );
}
