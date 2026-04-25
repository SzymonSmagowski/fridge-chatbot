"use client";
import { Check, Mic, Send, Sparkles } from "lucide-react";
import { useState } from "react";
import styles from "../preview.module.css";
import { MemberAvatar } from "./MemberAvatar";
import { MOCK_CHAT, MOCK_SUGGESTIONS, getMember } from "./mock-data";
import type { ChatMessage, ToolCall } from "./types";

export function ChatView() {
  const [input, setInput] = useState("");

  return (
    <section
      className={styles.view}
      role="tabpanel"
      id="view-chat"
      aria-labelledby="tab-chat"
    >
      <div className={styles.chatWrap}>
        <div className={styles.chatHero}>
          <div className={styles.aiCrest} aria-hidden="true">
            <Sparkles size={28} strokeWidth={2} color="#fff" />
          </div>
          <h3>Fridge Assistant</h3>
          <p>Ask about recipes, add to the shopping list, plan the week.</p>
        </div>

        <div className={styles.chatScroll}>
          {MOCK_CHAT.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        </div>

        <div className={styles.suggestions}>
          {MOCK_SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              className={styles.suggestion}
              onClick={() => setInput(s)}
            >
              {s}
            </button>
          ))}
        </div>

        <form
          className={styles.chatComposer}
          onSubmit={(e) => {
            e.preventDefault();
            setInput("");
          }}
        >
          <button
            type="button"
            className={`${styles.iconBtn} ${styles.mic}`}
            aria-label="Voice input (coming in v1.1)"
            title="Voice input is deferred to v1.1 — see docs/specs/fridge-chatbot/_manifest.md"
            disabled
          >
            <Mic size={20} strokeWidth={2} />
          </button>
          <input
            className={styles.input}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything, or say: 'Ola, add milk to the shopping list'…"
            aria-label="Message the fridge assistant"
          />
          <button
            type="submit"
            className={`${styles.iconBtn} ${styles.send}`}
            aria-label="Send"
          >
            <Send size={20} strokeWidth={2.4} />
          </button>
        </form>
      </div>
    </section>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const author = getMember(message.authorMemberId);

  return (
    <div className={`${styles.msg} ${isUser ? styles.user : styles.ai}`}>
      {isUser && author ? (
        <MemberAvatar initials={author.initials} color={author.color} size="md" />
      ) : !isUser ? (
        <span className={styles.avatar} aria-hidden="true">
          <Sparkles size={16} strokeWidth={2} color="#fff" />
        </span>
      ) : null}
      <div>
        <div className={styles.bubble}>
          {message.content}
          {message.toolCalls?.map((tc) => (
            <ToolCallCard key={tc.id} toolCall={tc} />
          ))}
        </div>
      </div>
    </div>
  );
}

function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  return (
    <div className={styles.toolCard} role="group" aria-label={`${toolCall.label}: ${toolCall.text}`}>
      <div className={styles.toolIcon} aria-hidden="true">
        <Sparkles size={14} strokeWidth={2.4} />
      </div>
      <div className={styles.toolBody}>
        <div className={styles.toolLabel}>{toolCall.label}</div>
        <div className={styles.toolText}>{toolCall.text}</div>
      </div>
      <div
        className={`${styles.toolStatus} ${
          toolCall.status === "failed" ? styles.toolStatusFailed : styles.toolStatusDone
        }`}
      >
        <Check size={14} strokeWidth={3} />
        {toolCall.status === "done" ? "Done" : toolCall.status === "failed" ? "Failed" : "Pending"}
      </div>
    </div>
  );
}
