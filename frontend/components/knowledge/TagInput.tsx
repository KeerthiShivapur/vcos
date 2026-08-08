"use client";

import { useState } from "react";
import { X } from "lucide-react";

export function TagInput({
  name,
  defaultValue = [],
  placeholder = "Add a tag and press Enter",
}: {
  name: string;
  defaultValue?: string[];
  placeholder?: string;
}) {
  const [tags, setTags] = useState<string[]>(defaultValue);
  const [draft, setDraft] = useState("");

  function addTag(raw: string) {
    const tag = raw.trim().replace(/^#/, "").toLowerCase();
    if (tag && !tags.includes(tag)) setTags((prev) => [...prev, tag]);
    setDraft("");
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 rounded-lg border border-line bg-canvas px-2.5 py-2 focus-within:border-brand">
        {tags.map((tag) => (
          <span key={tag} className="flex items-center gap-1 rounded-md bg-brand-soft px-2 py-0.5 text-[12px] font-medium text-brand">
            #{tag}
            <button
              type="button"
              onClick={() => setTags((prev) => prev.filter((t) => t !== tag))}
              className="text-brand/60 hover:text-brand"
              aria-label={`Remove ${tag}`}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          className="min-w-[120px] flex-1 bg-transparent py-0.5 text-sm text-ink outline-none placeholder:text-faint"
          placeholder={placeholder}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              addTag(draft);
            } else if (e.key === "Backspace" && !draft && tags.length) {
              setTags((prev) => prev.slice(0, -1));
            }
          }}
          onBlur={() => addTag(draft)}
        />
      </div>
      <input type="hidden" name={name} value={JSON.stringify(tags)} />
      <p className="mt-1 text-[11px] text-faint">{tags.length} tag{tags.length === 1 ? "" : "s"} selected</p>
    </div>
  );
}
