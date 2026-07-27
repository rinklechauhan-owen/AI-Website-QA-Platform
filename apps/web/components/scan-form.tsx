"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { createScan } from "@/lib/api";
import { MODULE_KEYS, MODULE_LABELS, type ModuleKey } from "@/lib/types";

// Phase 1 modules (PRD §22) are the ones enabled by default.
const DEFAULT_MODULES: ModuleKey[] = ["crawl", "seo", "accessibility", "images", "performance"];

export function ScanForm() {
  const [url, setUrl] = useState("");
  const [modules, setModules] = useState<ModuleKey[]>(DEFAULT_MODULES);

  const mutation = useMutation({
    mutationFn: () => createScan({ url, modules }),
  });

  function toggleModule(key: ModuleKey) {
    setModules((current) =>
      current.includes(key) ? current.filter((m) => m !== key) : [...current, key],
    );
  }

  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <div className="flex flex-col gap-2">
        <label htmlFor="url" className="text-sm font-medium">
          Website URL
        </label>
        <input
          id="url"
          type="url"
          required
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://example.com"
          className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-muted) px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        />
      </div>

      <fieldset className="flex flex-col gap-3">
        <legend className="text-sm font-medium">Modules</legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {MODULE_KEYS.map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={modules.includes(key)}
                onChange={() => toggleModule(key)}
                // Module 1 feeds every other module, so it is not optional.
                disabled={key === "crawl"}
              />
              {MODULE_LABELS[key]}
            </label>
          ))}
        </div>
      </fieldset>

      <button
        type="submit"
        disabled={mutation.isPending || url.trim() === ""}
        className="rounded-lg bg-blue-600 px-5 py-3 font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {mutation.isPending ? "Starting scan…" : "Start Scan"}
      </button>

      {mutation.isError && (
        <p role="alert" className="text-sm text-(--color-severity-high)">
          {mutation.error.message}
        </p>
      )}

      {mutation.isSuccess && (
        <p className="text-sm text-(--color-ink-muted)">
          Scan queued — <code>{mutation.data.id}</code>
        </p>
      )}
    </form>
  );
}
