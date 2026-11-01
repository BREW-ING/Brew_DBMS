"use client";

import { useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, CheckCircle2, Plus, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { profileSchema, type ProfileFormValues } from "@/lib/profile-schema";
import { cn } from "@/lib/utils";

type SaveResponse = { profile: ProfileFormValues };

const proficiencyLabels = ["Beginner", "Basic", "Intermediate", "Advanced", "Expert"] as const;

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-destructive">
      {message}
    </p>
  );
}

function ChipInput({
  id,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");

  function commit() {
    const item = draft.trim().replace(/,$/, "");
    if (item && !value.some((v) => v.toLowerCase() === item.toLowerCase())) {
      onChange([...value, item]);
    }
    setDraft("");
  }

  return (
    <div className="space-y-2">
      {value.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="Interests">
          {value.map((item) => (
            <li key={item}>
              <Badge variant="secondary" className="gap-1 pr-1">
                {item}
                <button
                  type="button"
                  aria-label={`Remove ${item}`}
                  onClick={() => onChange(value.filter((v) => v !== item))}
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
        id={id}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
            onChange(value.slice(0, -1));
          }
        }}
      />
    </div>
  );
}

export function SkillForm({ defaultValues }: { defaultValues: ProfileFormValues }) {
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isDirty, isSubmitting },
    reset,
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      skills: defaultValues.skills,
      interests: defaultValues.interests,
      teamSize: defaultValues.teamSize,
      hoursAvailable: defaultValues.hoursAvailable,
    },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "skills" });

  async function onSubmit(values: ProfileFormValues) {
    setSaveError(null);
    try {
      const res = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { profile } = (await res.json()) as SaveResponse;
      // The server normalizes names, so its copy becomes the new baseline.
      reset(profile);
      setSavedAt(new Date());
    } catch {
      setSavedAt(null);
      setSaveError("Couldn't save your profile. Try again in a moment.");
    }
  }

  const skillsError = errors.skills?.root?.message ?? errors.skills?.message;

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-8">
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="font-medium">Skills</h2>
            <p className="text-sm text-muted-foreground">Rate each from 1 (beginner) to 5 (expert).</p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => append({ name: "", proficiency: 3 })}>
            <Plus />
            Add skill
          </Button>
        </div>

        {fields.length > 0 ? (
          <ul className="space-y-2">
            {fields.map((field, index) => {
              const nameError = errors.skills?.[index]?.name?.message;
              const nameId = `skills-${index}-name`;
              return (
                <li key={field.id} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Label htmlFor={nameId} className="sr-only">
                      Skill {index + 1}
                    </Label>
                    <Input
                      id={nameId}
                      placeholder="e.g. TypeScript"
                      aria-invalid={nameError ? true : undefined}
                      aria-describedby={nameError ? `${nameId}-error` : undefined}
                      {...register(`skills.${index}.name`)}
                    />
                    <Label htmlFor={`skills-${index}-proficiency`} className="sr-only">
                      Proficiency for skill {index + 1}
                    </Label>
                    <select
                      id={`skills-${index}-proficiency`}
                      className="h-9 w-32 shrink-0 rounded-md border border-input bg-background px-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:w-40"
                      {...register(`skills.${index}.proficiency`, { valueAsNumber: true })}
                    >
                      {proficiencyLabels.map((label, i) => (
                        <option key={label} value={i + 1}>
                          {i + 1} · {label}
                        </option>
                      ))}
                    </select>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove skill ${index + 1}`}
                      onClick={() => remove(index)}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                  <FieldError id={`${nameId}-error`} message={nameError} />
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
            No skills yet. Add one so we can match you with problems.
          </div>
        )}
        <FieldError id="skills-error" message={skillsError} />
      </section>

      <section className="space-y-3">
        <div>
          <Label htmlFor="interests" className="font-medium">
            Interests
          </Label>
          <p className="mt-1 text-sm text-muted-foreground">Press Enter or comma to add a topic.</p>
        </div>
        <Controller
          control={control}
          name="interests"
          render={({ field }) => (
            <ChipInput
              id="interests"
              value={field.value}
              onChange={field.onChange}
              placeholder="e.g. climate, healthtech"
            />
          )}
        />
        <FieldError id="interests-error" message={errors.interests?.message} />
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="teamSize">Team size</Label>
          <Input
            id="teamSize"
            type="number"
            inputMode="numeric"
            min={1}
            max={10}
            aria-invalid={errors.teamSize ? true : undefined}
            aria-describedby={errors.teamSize ? "teamSize-error" : undefined}
            {...register("teamSize", { valueAsNumber: true })}
          />
          <FieldError id="teamSize-error" message={errors.teamSize?.message} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="hoursAvailable">Hours available</Label>
          <Input
            id="hoursAvailable"
            type="number"
            inputMode="numeric"
            min={1}
            max={168}
            aria-invalid={errors.hoursAvailable ? true : undefined}
            aria-describedby={errors.hoursAvailable ? "hoursAvailable-error" : undefined}
            {...register("hoursAvailable", { valueAsNumber: true })}
          />
          <FieldError id="hoursAvailable-error" message={errors.hoursAvailable?.message} />
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3 border-t pt-6">
        <Button type="submit" disabled={isSubmitting || !isDirty}>
          Save profile
        </Button>
        <p
          aria-live="polite"
          className={cn(
            "flex items-center gap-1.5 text-sm",
            saveError ? "text-destructive" : "text-muted-foreground",
            !savedAt && !saveError && "sr-only",
          )}
        >
          {saveError ? (
            <>
              <AlertCircle className="size-4" aria-hidden />
              {saveError}
            </>
          ) : savedAt ? (
            <>
              <CheckCircle2 className="size-4 text-primary" aria-hidden />
              Saved
            </>
          ) : null}
        </p>
      </div>
    </form>
  );
}
