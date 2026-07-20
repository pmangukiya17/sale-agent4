import { useState, type KeyboardEvent } from "react";

/** Free-text tag list editor for JSONB string[] fields (keywords, ports,
 * certifications, incoterms, ...). Press Enter or "," to add a tag.
 * Restyled to the permanent dark design-system tokens in M8.7 Phase E,
 * same reasoning as FormSection.tsx's own docstring: no OS-conditional
 * `dark:` classes, one dark theme throughout. */
export function TagInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  const addTag = () => {
    const tag = draft.trim();
    if (tag && !value.includes(tag)) {
      onChange([...value, tag]);
    }
    setDraft("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTag();
    } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border-hairline bg-surface-2 px-2 py-2 focus-within:ring-2 focus-within:ring-accent-primary">
      {value.map((tag) => (
        <span
          key={tag}
          className="flex items-center gap-1 rounded-pill bg-surface-3 px-2.5 py-1 text-xs font-medium text-slate-200"
        >
          {tag}
          <button
            type="button"
            onClick={() => onChange(value.filter((t) => t !== tag))}
            className="text-slate-500 hover:text-slate-100"
          >
            ×
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={addTag}
        placeholder={value.length === 0 ? placeholder : undefined}
        className="min-w-[120px] flex-1 border-none bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
      />
    </div>
  );
}
