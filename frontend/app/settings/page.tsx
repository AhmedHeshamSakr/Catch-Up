"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, KeyRound, AlertTriangle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export default function SettingsPage() {
  const [loaded, setLoaded] = useState(false);
  const [keySet, setKeySet] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [port, setPort] = useState("");
  const [loadedPort, setLoadedPort] = useState<number | null>(null);
  const [shadowed, setShadowed] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .getSettings()
      .then((s) => {
        if (!active) return;
        setKeySet(s.gemini_key_set);
        setLoadedPort(s.app_port);
        setPort(String(s.app_port));
        setShadowed(s.shadowed_keys ?? []);
        setLoaded(true);
      })
      .catch(() => {
        if (active) toast.error("Couldn't load settings", {
          description: "Is the app running?",
        });
      });
    return () => {
      active = false;
    };
  }, []);

  const onSave = async () => {
    // Only send what actually changed: a non-empty key, and a port that differs.
    const patch: { google_api_key?: string; app_port?: number } = {};
    if (keyInput.trim()) patch.google_api_key = keyInput.trim();
    const portNum = Number(port);
    if (port.trim() && Number.isFinite(portNum) && portNum !== loadedPort) {
      patch.app_port = portNum;
    }

    setSaving(true);
    try {
      const res = await api.putSettings(patch);
      if (patch.google_api_key) {
        setKeySet(true);
        setKeyInput("");
      }
      if (patch.app_port !== undefined) setLoadedPort(patch.app_port);

      const bits: string[] = [];
      if (res.applied.includes("google_api_key")) bits.push("Gemini key applied.");
      if (res.restart_required.includes("app_port"))
        bits.push("Port saved — restart the app to apply.");
      toast.success("Settings saved", {
        description: bits.join(" ") || "No changes.",
      });
    } catch (e) {
      const msg =
        e instanceof ApiError && e.status === 403
          ? "Settings can only be changed from this machine."
          : e instanceof ApiError && e.status === 422
            ? "Port must be between 1024 and 65535."
            : "Couldn't save settings.";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Settings" subtitle="Local configuration for this machine" />

      {loaded && shadowed.length > 0 && (
        <div className="flex max-w-xl items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800/40 dark:bg-amber-950/20 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            A root <code>.env</code> is overriding <code>app/.env</code> for{" "}
            <strong>{shadowed.join(", ")}</strong>. Saves here won&apos;t take effect on the
            next launch until you remove {shadowed.length > 1 ? "those keys" : "that key"} from
            the root <code>.env</code>.
          </span>
        </div>
      )}

      {!loaded ? (
        <Skeleton className="h-48 rounded-xl w-full max-w-xl" />
      ) : (
        <Card className="max-w-xl">
          <CardContent className="flex flex-col gap-6 py-6">
            {/* Gemini API key */}
            <div className="flex flex-col gap-2">
              <Label htmlFor="gemini-key" className="gap-1.5">
                <KeyRound className="size-3.5 text-muted-foreground" aria-hidden="true" />
                Gemini API key
              </Label>
              <Input
                id="gemini-key"
                type="password"
                autoComplete="off"
                placeholder={keySet ? "•••••••••• (set — enter to replace)" : "Paste your key"}
                value={keyInput}
                onChange={(e) => setKeyInput(e.target.value)}
              />
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                {keySet ? (
                  <>
                    <CheckCircle2 className="size-3.5 text-emerald" aria-hidden="true" />
                    Key configured. Applies on the next run.
                  </>
                ) : (
                  "No key yet — get one free from Google AI Studio. Applies on the next run."
                )}
              </p>
            </div>

            {/* Port */}
            <div className="flex flex-col gap-2">
              <Label htmlFor="app-port">Port</Label>
              <Input
                id="app-port"
                type="number"
                min={1024}
                max={65535}
                value={port}
                onChange={(e) => setPort(e.target.value)}
                className="max-w-[10rem]"
              />
              <p className="text-xs text-muted-foreground">
                Restart the app to apply a port change.
              </p>
            </div>

            <div>
              <Button onClick={onSave} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
