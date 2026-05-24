"use client";

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { Wand2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { SourceConfig, SourceType, Category } from "@/lib/types";
import { CATEGORY_LABELS, SOURCE_TYPE_LABELS } from "@/lib/labels";
import { fieldsForType, validateSource } from "@/lib/sources";
import { api, ApiError } from "@/lib/api";

interface SourceFormDialogProps {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  source: SourceConfig | null;
  existingIds: string[];
  onSave: (s: SourceConfig) => Promise<void>;
}

interface FormState {
  id: string;
  type: SourceType;
  name: string;
  url: string;
  query: string;
  selector: string;
  lang: string;
  country: string;
  channelId: string;
  categoryHint: Category | "";
  enabled: boolean;
}

function blankForm(): FormState {
  return {
    id: "",
    type: "rss",
    name: "",
    url: "",
    query: "",
    selector: "",
    lang: "",
    country: "",
    channelId: "",
    categoryHint: "",
    enabled: true,
  };
}

function sourceToForm(s: SourceConfig): FormState {
  return {
    id: s.id,
    type: s.type,
    name: s.name,
    url: s.url ?? "",
    query: s.query ?? "",
    selector: s.selector ?? "",
    lang: s.lang ?? "",
    country: s.country ?? "",
    channelId: s.channel_id ?? "",
    categoryHint: s.category_hint ?? "",
    enabled: s.enabled,
  };
}

// -----------------------------------------------------------------------
// Inner form — mounted fresh each time open toggles (key-based reset).
// State is initialized from props once, no effect needed.
// -----------------------------------------------------------------------
interface SourceFormBodyProps {
  isAdd: boolean;
  initial: FormState;
  existingIds: string[];
  onSave: (s: SourceConfig) => Promise<void>;
  onClose: () => void;
}

function SourceFormBody({
  isAdd,
  initial,
  existingIds,
  onSave,
  onClose,
}: SourceFormBodyProps) {
  const [form, setForm] = useState<FormState>(initial);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [linkInput, setLinkInput] = useState("");
  const [resolving, setResolving] = useState(false);

  const set = useCallback(
    <K extends keyof FormState>(key: K, value: FormState[K]) =>
      setForm((prev) => ({ ...prev, [key]: value })),
    []
  );

  const fields = fieldsForType(form.type);

  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setForm((prev) => ({ ...prev, type: e.target.value as SourceType }));
    setErrors([]);
    setLinkInput("");
  };

  const handleResolve = async () => {
    setResolving(true);
    try {
      const r = await api.resolveSource(form.type, linkInput.trim());
      if (form.type === "youtube" && r.channel_id) {
        set("channelId", r.channel_id);
      }
      if (form.type === "rss" && r.url) {
        set("url", r.url);
      }
      if (r.name && form.name.trim() === "") {
        set("name", r.name);
      }
      toast.success("Resolved");
    } catch (e) {
      toast.error(
        e instanceof ApiError ? e.message : "Could not resolve that link"
      );
    } finally {
      setResolving(false);
    }
  };

  const handleSave = async () => {
    const draft = {
      id: form.id.trim(),
      name: form.name.trim(),
      type: form.type,
      url: form.url.trim() || null,
      query: form.query.trim() || null,
      selector: form.selector.trim() || null,
      channel_id: form.channelId.trim() || null,
    };

    const validationErrors = validateSource(draft);

    if (isAdd && draft.id && existingIds.includes(draft.id)) {
      validationErrors.push(`ID "${draft.id}" is already in use`);
    }

    if (validationErrors.length > 0) {
      setErrors(validationErrors);
      toast.error(validationErrors[0]);
      return;
    }

    const fullSource: SourceConfig = {
      id: draft.id,
      type: form.type,
      name: draft.name,
      url: form.type !== "youtube" ? draft.url : null,
      query: form.type !== "youtube" ? draft.query : null,
      selector: form.type !== "youtube" ? draft.selector : null,
      channel_id: form.type === "youtube" ? draft.channel_id : null,
      category_hint: form.categoryHint || null,
      lang: form.lang.trim() || null,
      country: form.country.trim() || null,
      enabled: form.enabled,
    };

    setSaving(true);
    try {
      await onSave(fullSource);
      onClose();
    } catch {
      // parent already shows toast; keep dialog open
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="flex flex-col gap-4 py-1">
        {/* Error list */}
        {errors.length > 0 && (
          <ul className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive space-y-0.5">
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        )}

        {/* ID */}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="src-id">ID</Label>
          <Input
            id="src-id"
            value={form.id}
            onChange={(e) => set("id", e.target.value)}
            disabled={!isAdd}
            placeholder="my-rss-source"
            className="font-mono"
            aria-invalid={errors.some((e) => /id/i.test(e))}
          />
          {!isAdd && (
            <p className="text-xs text-muted-foreground">
              ID cannot be changed after creation.
            </p>
          )}
        </div>

        {/* Name */}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="src-name">Name</Label>
          <Input
            id="src-name"
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
            placeholder="My News Feed"
            aria-invalid={errors.some((e) => /name/i.test(e))}
          />
        </div>

        {/* Type */}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="src-type">Type</Label>
          <select
            id="src-type"
            value={form.type}
            onChange={handleTypeChange}
            className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
          >
            {(Object.keys(SOURCE_TYPE_LABELS) as SourceType[]).map((t) => (
              <option key={t} value={t}>
                {SOURCE_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </div>

        {/* Paste-a-link resolve row — youtube and rss only */}
        {(form.type === "youtube" || form.type === "rss") && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="src-link-input">
              {form.type === "youtube" ? "Channel URL or @handle" : "Site or feed URL"}
            </Label>
            <div className="flex gap-2">
              <Input
                id="src-link-input"
                value={linkInput}
                onChange={(e) => setLinkInput(e.target.value)}
                placeholder={
                  form.type === "youtube"
                    ? "Channel URL or @handle"
                    : "Site or feed URL"
                }
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                size="default"
                disabled={!linkInput.trim() || resolving}
                onClick={handleResolve}
                aria-label="Resolve link"
              >
                <Wand2 className="size-4" />
                {resolving ? "Resolving…" : "Resolve"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Paste a link and Resolve, or enter the value directly below.
            </p>
          </div>
        )}

        {/* Conditional fields */}
        {fields.includes("url") && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="src-url">URL</Label>
            <Input
              id="src-url"
              value={form.url}
              onChange={(e) => set("url", e.target.value)}
              placeholder="https://example.com/feed.xml"
              aria-invalid={errors.some((e) => /url/i.test(e))}
            />
          </div>
        )}

        {fields.includes("selector") && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="src-selector">CSS Selector</Label>
            <Input
              id="src-selector"
              value={form.selector}
              onChange={(e) => set("selector", e.target.value)}
              placeholder=".article-content"
              className="font-mono"
              aria-invalid={errors.some((e) => /selector/i.test(e))}
            />
          </div>
        )}

        {fields.includes("query") && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="src-query">Query</Label>
            <Input
              id="src-query"
              value={form.query}
              onChange={(e) => set("query", e.target.value)}
              placeholder="AI technology news"
              aria-invalid={errors.some((e) => /query/i.test(e))}
            />
          </div>
        )}

        {fields.includes("lang") && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="src-lang">Language (optional)</Label>
            <Input
              id="src-lang"
              value={form.lang}
              onChange={(e) => set("lang", e.target.value)}
              placeholder="en"
            />
          </div>
        )}

        {fields.includes("country") && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="src-country">Country (optional)</Label>
            <Input
              id="src-country"
              value={form.country}
              onChange={(e) => set("country", e.target.value)}
              placeholder="us"
            />
          </div>
        )}

        {fields.includes("channel_id") && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="src-channel-id">Channel ID</Label>
            <Input
              id="src-channel-id"
              value={form.channelId}
              onChange={(e) => set("channelId", e.target.value)}
              placeholder="UCxxxxxxxxxxxxxxxxxxxxxx"
              className="font-mono"
              aria-invalid={errors.some((e) => /channel id/i.test(e))}
            />
          </div>
        )}

        {/* Category hint */}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="src-category">Category hint (optional)</Label>
          <select
            id="src-category"
            value={form.categoryHint}
            onChange={(e) =>
              set("categoryHint", e.target.value as Category | "")
            }
            className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
          >
            <option value="">No category</option>
            {(Object.entries(CATEGORY_LABELS) as [Category, string][]).map(
              ([val, label]) => (
                <option key={val} value={val}>
                  {label}
                </option>
              )
            )}
          </select>
        </div>

        {/* Enabled toggle */}
        <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
          <div>
            <p className="text-sm font-medium">Enabled</p>
            <p className="text-xs text-muted-foreground">
              Disabled sources are skipped during collection
            </p>
          </div>
          <Switch
            checked={form.enabled}
            onCheckedChange={(checked) => set("enabled", checked)}
            aria-label="Enable source"
          />
        </div>
      </div>

      <DialogFooter showCloseButton>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : isAdd ? "Add source" : "Save changes"}
        </Button>
      </DialogFooter>
    </>
  );
}

// -----------------------------------------------------------------------
// Public export — shell that passes a key so form resets on open/close.
// -----------------------------------------------------------------------
export function SourceFormDialog({
  open,
  onOpenChange,
  source,
  existingIds,
  onSave,
}: SourceFormDialogProps) {
  const isAdd = source === null;
  const formKey = open ? `open-${source?.id ?? "new"}` : "closed";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md overflow-y-auto max-h-[90dvh]">
        <DialogHeader>
          <DialogTitle>{isAdd ? "Add source" : "Edit source"}</DialogTitle>
        </DialogHeader>
        <SourceFormBody
          key={formKey}
          isAdd={isAdd}
          initial={source ? sourceToForm(source) : blankForm()}
          existingIds={existingIds}
          onSave={onSave}
          onClose={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
