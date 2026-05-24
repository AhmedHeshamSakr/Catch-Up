"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { addTag } from "@/lib/tags";
import { cn } from "@/lib/utils";

interface TagEditorProps {
  label: string;
  description?: string;
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  inputId?: string;
}

export function TagEditor({
  label,
  description,
  values,
  onChange,
  placeholder = "Add tag…",
  inputId,
}: TagEditorProps) {
  const [inputValue, setInputValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const id = inputId ?? `tag-editor-${label.toLowerCase().replace(/\s+/g, "-")}`;

  function commit(raw: string) {
    const next = addTag(values, raw);
    if (next !== values) {
      onChange(next);
    }
    setInputValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit(inputValue);
    } else if (e.key === "Backspace" && inputValue === "" && values.length > 0) {
      // Remove last chip on backspace when input is empty
      onChange(values.slice(0, -1));
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    // If user typed a comma, treat it as a delimiter
    if (val.endsWith(",")) {
      commit(val.slice(0, -1));
    } else {
      setInputValue(val);
    }
  }

  function removeTag(index: number) {
    onChange(values.filter((_, i) => i !== index));
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      {description && (
        <p className="text-xs text-muted-foreground -mt-1">{description}</p>
      )}

      {/* Chips */}
      {values.length === 0 ? (
        <p className="text-xs text-muted-foreground italic">No items yet.</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {values.map((value, i) => (
            <span
              key={i}
              className={cn(
                "inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5",
                "text-xs font-medium text-foreground"
              )}
            >
              {value}
              <button
                type="button"
                aria-label={`Remove ${value}`}
                onClick={() => removeTag(i)}
                className="flex items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              >
                <X className="size-3" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Input */}
      <Input
        ref={inputRef}
        id={id}
        value={inputValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
      />
    </div>
  );
}
