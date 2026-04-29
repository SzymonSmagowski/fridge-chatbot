/**
 * Apple-Notes-style title/body split.
 *
 * The backend stores a single `content` string. By convention the first line
 * is the title (rendered larger), and the rest is the body. These helpers
 * keep the convention in one place so editor + list + hero stay in sync.
 */

export interface TitleBody {
  title: string;
  body: string;
}

export function splitTitleAndBody(content: string): TitleBody {
  const trimmedStart = content.replace(/^\s+/, "");
  const newlineIdx = trimmedStart.indexOf("\n");
  if (newlineIdx === -1) return { title: trimmedStart.trimEnd(), body: "" };
  return {
    title: trimmedStart.slice(0, newlineIdx).trim(),
    body: trimmedStart.slice(newlineIdx + 1).replace(/^\n+/, ""),
  };
}

export function joinTitleAndBody({ title, body }: TitleBody): string {
  const t = title.trim();
  if (!t && !body) return "";
  // Title-less notes (e.g. shopping list during early typing) shouldn't get a
  // leading newline — that would shift every line down on next reload.
  if (!t) return body;
  if (!body) return t;
  return `${t}\n${body}`;
}

export function isEmptyContent(content: string): boolean {
  return content.trim().length === 0;
}

export function previewLine(body: string, max = 60): string {
  const flat = body.replace(/\n+/g, " ").trim();
  if (flat.length <= max) return flat;
  return `${flat.slice(0, max - 1).trimEnd()}…`;
}

/**
 * Shopping-list items <-> string helpers. Items are stored as one-per-line
 * inside `note.content`. Empty lines become empty items while editing
 * (so the user can see a blank row they're typing into); on save we filter
 * empties at the boundary via `joinItems`.
 */
export function splitItems(content: string): string[] {
  if (!content) return [];
  return content.split("\n");
}

export function joinItems(items: string[]): string {
  return items
    .map((it) => it.replace(/\n/g, " "))
    .filter((it, i, arr) => it.trim().length > 0 || i === arr.length - 1)
    .join("\n");
}
