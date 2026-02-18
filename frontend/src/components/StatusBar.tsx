export function StatusBar({
  total,
  filtered,
  loading,
  error,
}: {
  total: number;
  filtered: number;
  loading: boolean;
  error: string | null;
}) {
  return (
    <div className="status-bar">
      {error ? (
        <span className="status-error">Error: {error}</span>
      ) : loading ? (
        <span className="status-loading">Loading markets…</span>
      ) : (
        <span>
          {filtered} of {total} markets
          {filtered < total && " (filtered)"}
        </span>
      )}
    </div>
  );
}
