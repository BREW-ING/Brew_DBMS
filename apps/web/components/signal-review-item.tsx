"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Archive, ExternalLink, Pencil, Trash2, X } from "lucide-react";

import { SourceBadge } from "@/components/source-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LOW_CONFIDENCE, signalSkillsSchema } from "@/lib/curator-schema";
import type { ReviewSignal, SignalTag } from "@/lib/review";
import { cn, formatAge } from "@/lib/utils";

function percent(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

function TagList({ tags }: { tags: SignalTag[] }) {
  if (tags.length === 0) return <p className="text-sm text-muted-foreground">No skill tags.</p>;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Skill tags">
      {tags.map((tag) => (
        <li key={tag.name}>
          <Badge variant={tag.confidence < LOW_CONFIDENCE ? "destructive" : "secondary"}>
            {tag.name}
            <span className="font-normal opacity-70">{percent(tag.confidence)}</span>
          </Badge>
        </li>
      ))}
    </ul>
  );
}

function TagEditor({
  signalId,
  initial,
  skillOptionsId,
  onSaved,
  onCancel,
}: {
  signalId: string;
  initial: string[];
  skillOptionsId: string;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [tags, setTags] = useState(initial);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputId = `signal-${signalId}-tag`;

  function commit() {
    const item = draft.trim().replace(/,$/, "");
    if (item && !tags.some((t) => t.toLowerCase() === item.toLowerCase())) setTags([...tags, item]);
    setDraft("");
  }

  async function save() {
    // Include a half-typed tag rather than silently dropping it.
    const pending = draft.trim();
    const next = pending && !tags.includes(pending) ? [...tags, pending] : tags;
    const parsed = signalSkillsSchema.safeParse({ skills: next });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid tags");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/curator/signals/${signalId}/skills`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      onSaved();
    } catch {
      setError("Couldn't save the tags. Try again in a moment.");
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border bg-muted/40 p-3">
      <Label htmlFor={inputId}>Skill tags</Label>
      {tags.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="Tags to save">
          {tags.map((tag) => (
            <li key={tag}>
              <Badge variant="secondary" className="gap-1 pr-1">
                {tag}
                <button
                  type="button"
                  aria-label={`Remove ${tag}`}
                  onClick={() => setTags(tags.filter((t) => t !== tag))}
                  className="rounded-sm p-0.5 hover:bg-foreground/10"
                >
                  <X aria-hidden />
                </button>
              </Badge>
            </li>
          ))}
        </ul>
      ) : null}
      <Input
        id={inputId}
        list={skillOptionsId}
        value={draft}
        placeholder="Add a skill, then Enter"
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && draft === "" && tags.length > 0) {
            setTags(tags.slice(0, -1));
          }
        }}
      />
      <p className="text-xs text-muted-foreground">Saved tags are stored at 100% confidence.</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={save} disabled={saving}>
          Save tags
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <p aria-live="polite" className="text-sm text-destructive">
          {error}
        </p>
      </div>
    </div>
  );
}

export function SignalReviewItem({ signal, skillOptionsId }: { signal: ReviewSignal; skillOptionsId: string }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isSeed = signal.url === null;

  async function mutate(init: RequestInit, failure: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/curator/signals/${signal.id}`, init);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // Re-run the page query so filters and counts reflect the change.
      router.refresh();
    } catch {
      setError(failure);
    } finally {
      setBusy(false);
      setConfirmingDelete(false);
    }
  }

  return (
    <article className={cn("space-y-3 rounded-xl border bg-card p-4 shadow-xs", signal.isStale && "opacity-75")}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <SourceBadge source={signal.source} className="text-foreground" />
        <time dateTime={signal.publishedAt} title={signal.publishedAt}>
          {formatAge(signal.publishedAt)}
        </time>
        {signal.isStale ? <Badge variant="outline">Stale</Badge> : null}
        {isSeed ? <Badge variant="outline">Seed</Badge> : null}
        {!signal.embedded ? <Badge variant="outline">Not embedded</Badge> : null}
        {signal.avgConfidence !== null ? (
          <span className={cn(signal.avgConfidence < LOW_CONFIDENCE && "font-medium text-destructive")}>
            avg confidence {percent(signal.avgConfidence)}
          </span>
        ) : null}
      </div>

      <h2 className="leading-snug font-medium">
        {signal.url ? (
          <a href={signal.url} target="_blank" rel="noreferrer" className="inline-flex items-start gap-1 hover:underline">
            {signal.title}
            <ExternalLink className="mt-1 size-3.5 shrink-0 text-muted-foreground" aria-label="(opens in a new tab)" />
          </a>
        ) : (
          signal.title
        )}
      </h2>

      {editing ? (
        <TagEditor
          signalId={signal.id}
          initial={signal.skills.map((s) => s.name)}
          skillOptionsId={skillOptionsId}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            router.refresh();
          }}
        />
      ) : (
        <TagList tags={signal.skills} />
      )}

      <div className="flex flex-wrap items-center gap-2 border-t pt-3">
        {!editing ? (
          <Button type="button" variant="outline" size="sm" onClick={() => setEditing(true)} disabled={busy}>
            <Pencil aria-hidden />
            Edit tags
          </Button>
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy || signal.isStale}
          onClick={() =>
            mutate(
              {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ isStale: true }),
              },
              "Couldn't mark the signal stale.",
            )
          }
        >
          <Archive aria-hidden />
          {signal.isStale ? "Stale" : "Mark stale"}
        </Button>
        {confirmingDelete ? (
          <>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={busy}
              onClick={() => mutate({ method: "DELETE" }, "Couldn't delete the signal.")}
            >
              <Trash2 aria-hidden />
              Confirm delete
            </Button>
            <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => setConfirmingDelete(false)}>
              Keep
            </Button>
          </>
        ) : (
          <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => setConfirmingDelete(true)}>
            <Trash2 aria-hidden />
            Delete
          </Button>
        )}
        <p aria-live="polite" className="text-sm text-destructive">
          {error}
        </p>
      </div>
      {confirmingDelete ? (
        <p className="text-xs text-muted-foreground">
          Deleting also removes its suggestions and their feedback.
          {isSeed ? null : " The next fetch can bring it back if the source still lists it; mark it stale to retire it for good."}
        </p>
      ) : null}
    </article>
  );
}
