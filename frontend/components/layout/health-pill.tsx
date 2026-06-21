"use client";

import { useEffect, useState } from "react";
import { apiHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

type Status = "online" | "offline" | "checking";

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
      // Shared helper: same API_BASE + X-API-Key as every other call.
      apiHealth(ctrl.signal)
        .then((ok) => {
          clearTimeout(timer);
          if (mounted) setStatus(ok ? "online" : "offline");
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
