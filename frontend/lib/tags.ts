/**
 * Pure helper for tag-editor deduplication.
 * Returns a new array with the trimmed raw string appended,
 * or the original array if raw is blank or already present
 * (case-insensitive comparison).
 */
export function addTag(values: string[], raw: string): string[] {
  const trimmed = raw.trim();
  if (!trimmed) return values;
  const lower = trimmed.toLowerCase();
  if (values.some((v) => v.toLowerCase() === lower)) return values;
  return [...values, trimmed];
}
