"use client";
import { Plus, X } from "lucide-react";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import styles from "./fridge.module.css";
import { joinItems, splitItems } from "./notes-content";
import { m } from "@/paraglide/messages.js";

export interface ShoppingListEditorProps {
  content: string;
  onChange: (nextContent: string) => void;
}

export interface ShoppingListEditorHandle {
  focusFirst: () => void;
}

/**
 * Items live in `note.content` joined by `\n`. Local state holds them as an
 * array so React can drive a per-row input — empty rows are allowed during
 * editing (the user might tap [+] then type), and `joinItems` filters
 * trailing/empty rows before persisting.
 */
export const ShoppingListEditor = forwardRef<ShoppingListEditorHandle, ShoppingListEditorProps>(
  function ShoppingListEditor({ content, onChange }, ref) {
    const initial = useMemo(() => {
      const items = splitItems(content);
      return items.length === 0 ? [""] : items;
    }, [content]);

    const [items, setItems] = useState<string[]>(initial);
    const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
    // Index of the row to focus after the next render. Used after add/delete
    // so the keyboard target follows the user's mental model.
    const focusOnRenderRef = useRef<number | null>(null);
    // Cursor caret position to restore alongside focus, used by Backspace-merge.
    const focusCaretRef = useRef<number | null>(null);

    // Adopt server-pushed updates only when the user isn't actively editing —
    // matches the pattern in note-editor-pane.tsx for normal notes.
    useEffect(() => {
      const incoming = splitItems(content);
      const incomingNorm = incoming.length === 0 ? [""] : incoming;
      if (joinItems(items) === joinItems(incomingNorm)) return;
      const focused = document.activeElement;
      const userIsEditing = inputRefs.current.some((el) => el === focused);
      if (!userIsEditing) setItems(incomingNorm);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [content]);

    useLayoutEffect(() => {
      const idx = focusOnRenderRef.current;
      if (idx === null) return;
      const el = inputRefs.current[idx];
      if (el) {
        el.focus();
        const caret = focusCaretRef.current;
        if (caret !== null) {
          el.setSelectionRange(caret, caret);
        }
      }
      focusOnRenderRef.current = null;
      focusCaretRef.current = null;
    });

    useImperativeHandle(ref, () => ({
      focusFirst: () => inputRefs.current[0]?.focus(),
    }));

    const commit = useCallback(
      (next: string[]) => {
        setItems(next);
        onChange(joinItems(next));
      },
      [onChange],
    );

    const updateAt = (idx: number, value: string) => {
      const next = items.slice();
      next[idx] = value;
      commit(next);
    };

    const insertAfter = (idx: number, value = "") => {
      const next = items.slice();
      next.splice(idx + 1, 0, value);
      focusOnRenderRef.current = idx + 1;
      focusCaretRef.current = 0;
      commit(next);
    };

    const removeAt = (idx: number) => {
      if (items.length === 1) {
        // Keep at least one empty row so the editor isn't a blank canvas.
        focusOnRenderRef.current = 0;
        focusCaretRef.current = 0;
        commit([""]);
        return;
      }
      const next = items.slice();
      next.splice(idx, 1);
      focusOnRenderRef.current = Math.max(0, idx - 1);
      focusCaretRef.current = next[Math.max(0, idx - 1)]?.length ?? 0;
      commit(next);
    };

    const handleKeyDown = (idx: number) => (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();
        insertAfter(idx);
        return;
      }
      if (e.key === "Backspace" && (e.currentTarget.value === "" || e.currentTarget.selectionStart === 0)) {
        // Empty row: delete it. Caret-at-start with content: merge into previous.
        if (e.currentTarget.value === "") {
          if (items.length === 1) return; // Don't kill the last row
          e.preventDefault();
          removeAt(idx);
          return;
        }
        if (idx > 0 && e.currentTarget.selectionStart === 0 && e.currentTarget.selectionEnd === 0) {
          e.preventDefault();
          const prevLen = items[idx - 1].length;
          const merged = items[idx - 1] + items[idx];
          const next = items.slice();
          next.splice(idx - 1, 2, merged);
          focusOnRenderRef.current = idx - 1;
          focusCaretRef.current = prevLen;
          commit(next);
        }
      }
    };

    const handleAddClick = () => {
      // Append at the end and focus the new input.
      insertAfter(items.length - 1);
    };

    return (
      <div className={styles.shoppingEditor}>
        <ul className={styles.shoppingItems} role="list">
          {items.map((item, idx) => (
            <li key={idx} className={styles.shoppingItem}>
              <input
                ref={(el) => {
                  inputRefs.current[idx] = el;
                }}
                className={styles.shoppingItemInput}
                value={item}
                onChange={(e) => updateAt(idx, e.target.value)}
                onKeyDown={handleKeyDown(idx)}
                placeholder={m.shopping_item_placeholder()}
                aria-label={m.shopping_item_aria({ index: String(idx + 1) })}
              />
              <button
                type="button"
                className={styles.shoppingItemRemove}
                onClick={() => removeAt(idx)}
                aria-label={m.shopping_item_remove_aria()}
                title={m.shopping_item_remove_aria()}
              >
                <X size={16} strokeWidth={2.4} />
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className={styles.shoppingAddButton}
          onClick={handleAddClick}
        >
          <Plus size={18} strokeWidth={2.4} />
          {m.shopping_add_item()}
        </button>
      </div>
    );
  },
);
