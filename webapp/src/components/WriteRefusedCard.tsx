import { useT } from "../i18n";
import { BOT_CHAT_URL } from "../lib/links";
import { openTelegramLink } from "../telegram";

/**
 * Shown after the user declined to let the bot write to them: its chat is where "Start" says yes.
 * `text` says what the bot cannot send without it.
 */
export function WriteRefusedCard({ text }: { text: string }) {
  const t = useT();
  return (
    <div className="card" role="alert">
      <h2 className="card__title">{t.reminderForm.writeTitle}</h2>
      <p>{text}</p>
      <button type="button" className="button" onClick={() => openTelegramLink(BOT_CHAT_URL)}>
        {t.reminderForm.openChat}
      </button>
    </div>
  );
}
