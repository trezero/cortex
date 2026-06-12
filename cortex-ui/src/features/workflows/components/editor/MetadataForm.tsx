interface MetadataFormProps {
  name: string;
  description: string;
  tags: string[];
  onChange: (field: string, value: string | string[]) => void;
}

export function MetadataForm({ name, description, tags, onChange }: MetadataFormProps) {
  function handleTagsChange(raw: string) {
    const parsed = raw
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    onChange("tags", parsed);
  }

  return (
    <div className="space-y-3">
      <div>
        <label htmlFor="wf-name" className="block text-sm text-gray-400 mb-1">
          Name
        </label>
        <input
          id="wf-name"
          type="text"
          value={name}
          onChange={(e) => onChange("name", e.target.value)}
          placeholder="my-workflow"
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-gray-200
            placeholder:text-gray-600 focus:border-cyan-500 focus:outline-none transition-colors"
        />
      </div>

      <div>
        <label htmlFor="wf-description" className="block text-sm text-gray-400 mb-1">
          Description
        </label>
        <textarea
          id="wf-description"
          value={description}
          onChange={(e) => onChange("description", e.target.value)}
          placeholder="Describe this workflow..."
          rows={2}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-gray-200
            placeholder:text-gray-600 focus:border-cyan-500 focus:outline-none transition-colors resize-none"
        />
      </div>

      <div>
        <label htmlFor="wf-tags" className="block text-sm text-gray-400 mb-1">
          Tags <span className="text-gray-600">(comma-separated)</span>
        </label>
        <input
          id="wf-tags"
          type="text"
          value={tags.join(", ")}
          onChange={(e) => handleTagsChange(e.target.value)}
          placeholder="deploy, backend, ci"
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-gray-200
            placeholder:text-gray-600 focus:border-cyan-500 focus:outline-none transition-colors"
        />
      </div>
    </div>
  );
}
