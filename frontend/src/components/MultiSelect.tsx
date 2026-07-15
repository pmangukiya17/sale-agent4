export interface MultiSelectOption {
  id: string;
  label: string;
}

/** Simple checkbox-list multi-select for reference data (industries, buyer
 * types, countries, languages). Deliberately not a fancy searchable
 * combobox - a scrollable checkbox list is faster to build correctly and
 * just as usable for lists of this size. */
export function MultiSelect({
  options,
  selected,
  onChange,
}: {
  options: MultiSelectOption[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const toggle = (id: string) => {
    if (selected.includes(id)) {
      onChange(selected.filter((s) => s !== id));
    } else {
      onChange([...selected, id]);
    }
  };

  return (
    <div className="max-h-48 overflow-y-auto rounded-md border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-800">
      {options.length === 0 && (
        <p className="px-2 py-1 text-sm text-slate-400">No options available.</p>
      )}
      {options.map((option) => (
        <label
          key={option.id}
          className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          <input
            type="checkbox"
            checked={selected.includes(option.id)}
            onChange={() => toggle(option.id)}
            className="h-4 w-4 rounded border-slate-300"
          />
          {option.label}
        </label>
      ))}
    </div>
  );
}
