import type { RefObject } from "react";
import { useT } from "../i18n";
import { BOT_CHAT_URL } from "../lib/links";
import { openTelegramLink } from "../telegram";

/**
 * Shown after the user declined to let the bot write to them: its chat is where "Start" says yes.
 * `text` says what the bot cannot send without it; `card` is useWriteAccess's own, which brings the
 * card into view after each refusal.
 */
export function WriteRefusedCard({ text, card }: { text: string; card: RefObject<HTMLDivElement | null> }) {
  const t = useT();
  return (
    <div ref={card} className="card write-refused" role="alert">
      <h2 className="card__title">{t.reminderForm.writeTitle}</h2>
      <p>{text}</p>
      <button type="button" className="button" onClick={() => openTelegramLink(BOT_CHAT_URL)}>
        {t.reminderForm.openChat}
      </button>
    </div>
  );
}
