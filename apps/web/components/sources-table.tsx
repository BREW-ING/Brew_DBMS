"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, Pencil } from "lucide-react";

import { SourceBadge, sourceLabel } from "@/components/source-badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { parseSourceConfig, type SourceUpdate } from "@/lib/curator-schema";
import type { IngestionSource } from "@/lib/sources";
import { cn, formatAge } from "@/lib/utils";

function formatConfig(config: IngestionSource["config"]): string {
  return JSON.stringify(config, null, 2);
}

async function patchSource(id: number, update: SourceUpdate): Promise<IngestionSource> {
  const res = await fetch(`/api/curator/sources/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as IngestionSource;
}

function ActiveSwitch({
  checked,
  disabled,
  label,
  onChange,
}: {
  checked: boolean;
  disabled: boolean;
  label: string;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-transparent transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50",
        checked ? "bg-primary" : "bg-input",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-4 rounded-full bg-background shadow-sm transition-transform",
          checked ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

function ConfigEditor({
  source,
  onSaved,
  onCancel,
}: {
  source: IngestionSource;
  onSaved: (source: IngestionSource) => void;
  onCancel: () => void;
}) {
  const original = formatConfig(source.config);
  const [text, setText] = useState(original);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const parsed = parseSourceConfig(text);
  const textareaId = `source-${source.id}-config`;
  const errorId = `${textareaId}-error`;

  async function save() {
    if (!parsed.ok) return;
    setSaving(true);
    setSaveError(null);
    try {
      onSaved(await patchSource(source.id, { config: parsed.config }));
    } catch {
      setSaveError("Couldn't save the config. Try again in a moment.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={textareaId}>Config for {sourceLabel(source.sourceType)} source #{source.id}</Label>
      <textarea
        id={textareaId}
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        rows={Math.min(16, Math.max(4, text.split("\n").length + 1))}
        aria-invalid={parsed.ok ? undefined : true}
        aria-describedby={parsed.ok ? undefined : errorId}
        className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-destructive"
      />
      {!parsed.ok ? (
        <p id={errorId} className="flex items-center gap-1.5 text-xs text-destructive">
          <AlertCircle className="size-3.5" aria-hidden />
          {parsed.error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={save} disabled={saving || !parsed.ok || text === original}>
          Save config
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!parsed.ok}
          onClick={() => parsed.ok && setText(formatConfig(parsed.config))}
        >
          Format
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <p aria-live="polite" className="text-sm text-destructive">
          {saveError}
        </p>
      </div>
    </div>
  );
}

function SourceRow({ initial }: { initial: IngestionSource }) {
  const [source, setSource] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const label = sourceLabel(source.sourceType);
  const keyCount = Object.keys(source.config).length;

  async function toggle(isActive: boolean) {
    setToggling(true);
    setStatus(null);
    try {
      setSource(await patchSource(source.id, { isActive }));
      setStatus({ ok: true, message: isActive ? "Enabled" : "Disabled" });
    } catch {
      setStatus({ ok: false, message: "Couldn't update. Try again." });
    } finally {
      setToggling(false);
    }
  }

  return (
    <>
      <tr className={cn("border-t", editing && "bg-muted/40")}>
        <td className="px-3 py-3">
          <SourceBadge source={source.sourceType} />
          <span className="ml-1.5 text-xs text-muted-foreground">#{source.id}</span>
        </td>
        <td className="px-3 py-3">
          <div className="flex items-center gap-2">
            <ActiveSwitch
              checked={source.isActive}
              disabled={toggling}
              label={`Fetch from ${label} source #${source.id}`}
              onChange={toggle}
            />
            <span
              aria-live="polite"
              className={cn("flex items-center gap-1 text-xs", status?.ok === false ? "text-destructive" : "text-muted-foreground")}
            >
              {status ? (
                <>
                  {status.ok ? <CheckCircle2 className="size-3.5 text-primary" aria-hidden /> : null}
                  {status.message}
                </>
              ) : null}
            </span>
          </div>
        </td>
        <td className="px-3 py-3 text-sm whitespace-nowrap text-muted-foreground">
          {source.lastFetchedAt ? (
            <time dateTime={source.lastFetchedAt} title={source.lastFetchedAt}>
              {formatAge(source.lastFetchedAt)}
            </time>
          ) : (
            "Never"
          )}
        </td>
        <td className="px-3 py-3">
          <div className="flex items-center justify-between gap-3">
            <code className="truncate font-mono text-xs text-muted-foreground" title={JSON.stringify(source.config)}>
              {keyCount === 0 ? "{} (adapter defaults)" : JSON.stringify(source.config)}
            </code>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-expanded={editing}
              aria-controls={`source-${source.id}-editor`}
              onClick={() => setEditing((v) => !v)}
            >
              <Pencil aria-hidden />
              {editing ? "Close" : "Edit"}
            </Button>
          </div>
        </td>
      </tr>
      {editing ? (
        <tr id={`source-${source.id}-editor`} className="bg-muted/40">
          <td colSpan={4} className="px-3 pb-4">
            <ConfigEditor
              source={source}
              onCancel={() => setEditing(false)}
              onSaved={(saved) => {
                setSource(saved);
                setEditing(false);
                setStatus({ ok: true, message: "Config saved" });
              }}
            />
          </td>
        </tr>
      ) : null}
    </>
  );
}

export function SourcesTable({ sources }: { sources: IngestionSource[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="w-full min-w-[40rem] table-fixed text-left">
        <colgroup>
          <col className="w-36" />
          <col className="w-40" />
          <col className="w-32" />
          <col />
        </colgroup>
        <thead className="bg-muted/50 text-xs font-medium text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2">Type</th>
            <th scope="col" className="px-3 py-2">Active</th>
            <th scope="col" className="px-3 py-2">Last fetched</th>
            <th scope="col" className="px-3 py-2">Config</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <SourceRow key={source.id} initial={source} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
