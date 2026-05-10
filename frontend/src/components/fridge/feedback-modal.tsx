"use client";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import {
  ApiError,
  feedbackApi,
  type FeedbackCategory,
} from "@/lib/api";
import { m } from "@/paraglide/messages.js";

export interface FeedbackModalProps {
  open: boolean;
  /**
   * Optional thread UUID to attach to the feedback row, so a reviewer can pull
   * the chat context when triaging. Pass the runtime's `threadUuid` when the
   * modal is opened from chat; pass `null` from settings/other contexts.
   */
  threadId?: string | null;
  onClose: () => void;
}

const CATEGORIES: ReadonlyArray<{
  value: FeedbackCategory;
  label: () => string;
}> = [
  { value: "bug", label: () => m.feedback_category_bug() },
  { value: "improvement", label: () => m.feedback_category_improvement() },
  { value: "question", label: () => m.feedback_category_question() },
  { value: "other", label: () => m.feedback_category_other() },
];

const MIN_LEN = 10;
const MAX_LEN = 2000;

/**
 * Modal form for filing a feedback ticket. Posts to `POST /api/feedback`,
 * surfaces 429 rate-limit responses with a friendlier toast than the generic
 * `http()` helper produces. On success, clears the form and closes.
 */
export function FeedbackModal({ open, threadId, onClose }: FeedbackModalProps) {
  const [category, setCategory] = useState<FeedbackCategory>("bug");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Reset form whenever the modal opens. Avoids leftover text from a previous
  // session if the user closes mid-edit and reopens. The setState calls below
  // are guarded by the `open` toggle and only fire on the rising edge, so the
  // cascading-render warning doesn't apply.
  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCategory("bug");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMessage("");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSubmitting(false);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, submitting]);

  if (!open) return null;

  const trimmed = message.trim();
  const tooShort = trimmed.length < MIN_LEN;
  const tooLong = message.length > MAX_LEN;
  const canSubmit = !submitting && !tooShort && !tooLong;

  const charState =
    message.length > MAX_LEN
      ? "error"
      : message.length > MAX_LEN - 200
      ? "warn"
      : "ok";

  const onSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await feedbackApi.submit({
        category,
        message: trimmed,
        thread_id: threadId ?? null,
      });
      toast.success(m.feedback_success_toast());
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        // The shared http() helper already pops a generic rate-limit toast for
        // 429s; we surface a feedback-specific message in addition because the
        // modal stays open and the user needs an explicit retry hint here.
        toast.error(m.feedback_rate_limit_toast());
      } else {
        const fallback = err instanceof ApiError ? err.message : null;
        toast.error(fallback ?? m.feedback_error_toast());
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className={styles.confirmDialogBackdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby="feedback-modal-title"
      aria-describedby="feedback-modal-desc"
      onClick={() => {
        if (!submitting) onClose();
      }}
    >
      <div
        className={styles.feedbackDialog}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="feedback-modal-title">{m.feedback_modal_title()}</h3>
        <p id="feedback-modal-desc">{m.feedback_modal_description()}</p>

        <fieldset
          style={{ border: "none", padding: 0, margin: 0 }}
          disabled={submitting}
        >
          <legend className="sr-only">
            {m.feedback_modal_title()}
          </legend>
          <div className={styles.feedbackCategoryGrid}>
            {CATEGORIES.map(({ value, label }) => {
              const checked = category === value;
              return (
                <label
                  key={value}
                  className={styles.feedbackCategoryOption}
                  data-checked={checked}
                >
                  <input
                    type="radio"
                    name="feedback-category"
                    value={value}
                    checked={checked}
                    onChange={() => setCategory(value)}
                  />
                  {label()}
                </label>
              );
            })}
          </div>
        </fieldset>

        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <textarea
            className={styles.feedbackTextarea}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={m.feedback_message_placeholder()}
            aria-label={m.feedback_message_placeholder()}
            disabled={submitting}
            maxLength={MAX_LEN + 100}
          />
          <div
            className={styles.feedbackCharCount}
            data-state={charState}
            aria-live="polite"
          >
            {message.length} / {MAX_LEN}
          </div>
        </div>

        <div className={styles.confirmActions}>
          <button
            type="button"
            className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
            onClick={onClose}
            disabled={submitting}
          >
            {m.feedback_cancel()}
          </button>
          <button
            type="button"
            className={`${styles.btn} ${styles.btnPrimary} ${styles.btnSmall}`}
            onClick={() => void onSubmit()}
            disabled={!canSubmit}
            aria-disabled={!canSubmit}
          >
            {submitting ? m.common_loading() : m.feedback_submit()}
          </button>
        </div>
      </div>
    </div>
  );
}
