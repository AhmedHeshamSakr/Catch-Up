"use client";

import { useState } from "react";
import { Play, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import type { VariantProps } from "class-variance-authority";

interface RunNowButtonProps extends VariantProps<typeof buttonVariants> {
  onStarted?: () => void;
}

export function RunNowButton({ onStarted, variant = "default", size = "default" }: RunNowButtonProps) {
  const [pending, setPending] = useState(false);

  async function handleClick() {
    setPending(true);
    try {
      const { run_id } = await api.triggerRun();
      toast.success("Digest run started", {
        description: `Run ${run_id.slice(0, 8)} is processing. Enrichment needs a Gemini API key on the server.`,
      });
      onStarted?.();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Single-flight: a digest is already running on the server.
        toast.error("A digest run is already in progress", {
          description: "Wait for the current run to finish before starting another.",
        });
      } else if (err instanceof ApiError) {
        toast.error("Couldn't start run", { description: err.message });
      } else {
        toast.error("Couldn't start run", { description: "An unexpected error occurred." });
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <Button
      variant={variant}
      size={size}
      disabled={pending}
      onClick={handleClick}
    >
      {pending ? (
        <Loader2 className="animate-spin" />
      ) : (
        <Play />
      )}
      Run now
    </Button>
  );
}
