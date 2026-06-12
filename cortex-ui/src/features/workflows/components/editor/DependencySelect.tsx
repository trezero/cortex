import { useRef, useState } from "react";

interface DependencySelectProps {
  selectedIds: string[];
  availableIds: string[];
  onChange: (ids: string[]) => void;
}

export function DependencySelect({ selectedIds, availableIds, onChange }: DependencySelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  function toggle(id: string) {
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter((s) => s !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  }

  function handleBlur(e: React.FocusEvent) {
    if (!containerRef.current?.contains(e.relatedTarget as Node)) {
      setOpen(false);
    }
  }

  if (availableIds.length === 0) {
    return <span className="text-xs text-gray-600 italic">No other nodes available</span>;
  }

  return (
    <div ref={containerRef} className="relative" onBlur={handleBlur}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-left
          text-gray-200 hover:border-cyan-500/40 focus:border-cyan-500 focus:outline-none transition-colors"
      >
        {selectedIds.length === 0 ? (
          <span className="text-gray-600">Select dependencies...</span>
        ) : (
          <span className="truncate">{selectedIds.join(", ")}</span>
        )}
      </button>

      {open && (
        <div
          className="absolute z-20 mt-1 w-full bg-gray-900/95 backdrop-blur-md border border-white/10
            rounded-lg shadow-lg max-h-48 overflow-y-auto"
        >
          {availableIds.map((id) => {
            const checked = selectedIds.includes(id);
            return (
              <label
                key={id}
                className="flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-white/5
                  cursor-pointer transition-colors"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(id)}
                  className="accent-cyan-500"
                />
                <span className="font-mono truncate">{id}</span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}
