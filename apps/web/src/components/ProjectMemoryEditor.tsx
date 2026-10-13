"use client";

import { useState } from "react";

type ProjectMemoryEditorProps = {
  initialValue: string;
  onSave: (value: string) => Promise<void>;
};

export function ProjectMemoryEditor({ initialValue, onSave }: ProjectMemoryEditorProps) {
  const [value, setValue] = useState(initialValue);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await onSave(value);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-label="Project memory">
      <h2>Project memory</h2>
      <p>Claude reads this file for every project run. Changes are saved only from this editor.</p>
      <textarea value={value} onChange={(event) => setValue(event.target.value)} rows={18} />
      <button type="button" onClick={save} disabled={saving}>
        {saving ? "Saving…" : "Save memory"}
      </button>
    </section>
  );
}
