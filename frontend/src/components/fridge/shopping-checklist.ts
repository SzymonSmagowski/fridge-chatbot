/**
 * Shopping-list checkbox semantics — frontend-only parsing per Architect §7.3 (D6).
 * Notes with the `shopping-list` label render their `content` as a checklist:
 *   `[x] foo` => done
 *   `[ ] foo` => pending
 *   `foo`     => pending
 *
 * Toggling a checkbox sends PATCH /notes/{id} with the rebuilt content string.
 */
export type ChecklistItem = { text: string; done: boolean };

const CHECKED_RE = /^\s*\[x\]\s+(.*)$/i;
const UNCHECKED_RE = /^\s*\[ \]\s+(.*)$/i;

export function parseChecklist(content: string): ChecklistItem[] {
  const out: ChecklistItem[] = [];
  for (const rawLine of content.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const checked = CHECKED_RE.exec(line);
    if (checked) {
      out.push({ text: checked[1].trim(), done: true });
      continue;
    }
    const unchecked = UNCHECKED_RE.exec(line);
    if (unchecked) {
      out.push({ text: unchecked[1].trim(), done: false });
      continue;
    }
    out.push({ text: line, done: false });
  }
  return out;
}

export function serializeChecklist(items: ChecklistItem[]): string {
  return items
    .map((it) => `${it.done ? "[x]" : "[ ]"} ${it.text}`)
    .join("\n");
}

export function toggleChecklistAt(content: string, index: number): string {
  const items = parseChecklist(content);
  if (index < 0 || index >= items.length) return content;
  items[index] = { ...items[index], done: !items[index].done };
  return serializeChecklist(items);
}

export function appendChecklistLine(content: string, line: string): string {
  const trimmed = line.trim();
  if (!trimmed) return content;
  return content ? `${content}\n[ ] ${trimmed}` : `[ ] ${trimmed}`;
}
