import { useDeleteMaterialization, useMaterializationHistory } from "../hooks/useMaterializationQueries";
import type { MaterializationRecord } from "../types";

interface MaterializationListProps {
  projectId?: string;
  statusFilter?: string;
}

export const MaterializationList = ({ projectId, statusFilter }: MaterializationListProps) => {
  const { data, isLoading } = useMaterializationHistory(projectId, statusFilter);
  const deleteMutation = useDeleteMaterialization();

  if (isLoading) {
    return <div className="text-gray-400 p-4">Loading materialization history...</div>;
  }

  const items = data?.items ?? [];

  if (items.length === 0) {
    return (
      <div className="text-gray-500 p-4 text-center">
        No materialized knowledge files yet. Agents will automatically materialize knowledge when they detect gaps in
        local context.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item: MaterializationRecord) => (
        <div
          key={item.id}
          className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 flex items-center justify-between"
        >
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-white font-medium">{item.topic}</span>
              <span
                className={`text-xs px-2 py-0.5 rounded ${
                  item.status === "active"
                    ? "bg-green-900/50 text-green-400"
                    : item.status === "pending"
                      ? "bg-blue-900/50 text-blue-400"
                      : item.status === "stale"
                        ? "bg-yellow-900/50 text-yellow-400"
                        : "bg-gray-700 text-gray-400"
                }`}
              >
                {item.status}
              </span>
            </div>
            <div className="text-sm text-gray-400 mt-1">
              {item.file_path} — {item.word_count} words — accessed {item.access_count} times
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              Materialized {new Date(item.materialized_at).toLocaleDateString()}
              {item.original_urls.length > 0 && ` from ${item.original_urls[0]}`}
            </div>
          </div>
          <button
            onClick={() => deleteMutation.mutate(item.id)}
            className="text-red-400 hover:text-red-300 text-sm px-3 py-1"
            disabled={deleteMutation.isPending}
            type="button"
          >
            Delete
          </button>
        </div>
      ))}
    </div>
  );
};
