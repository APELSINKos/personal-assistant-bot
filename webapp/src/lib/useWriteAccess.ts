import { useEffect, useRef, useState } from "react";
import { useAllowWrite } from "../api/queries";
import { requestWriteAccess } from "../telegram";

/**
 * A reminder or a lesson alert is a message from the bot, and the bot may write to the user only
 * after Telegram's "allow the bot to message you" dialog and the server's record of the answer.
 * `ensure()` runs that when the profile says the permission is missing and resolves to whether the
 * action that needs it may go on; while the profile is not loaded (`canWrite` is undefined) the
 * action goes on, and the server has the last word. `refused` is set by a refusal and cleared by
 * the next `ensure()` that lets the action go on, whichever way the permission came.
 *
 * `card` is for the screen's WriteRefusedCard. A refusal says nothing else, and its card may come
 * in out of sight: under the bottom bar, below the last thing of a long screen («Поделиться
 * прогнозом»), or at the top of a form read down to its end. Each refusal scrolls the page just
 * enough to show all of the card, above the bar (html's scroll-padding-bottom); a card only drawn
 * again, with no new refusal (another city's forecast under the same one), leaves the page where
 * it is.
 */
export function useWriteAccess(canWrite: boolean | undefined) {
  const allowWrite = useAllowWrite();
  const [refused, setRefused] = useState(false);
  // Every refusal, also one that finds `refused` up already: each brings the card in.
  const [refusals, setRefusals] = useState(0);
  const card = useRef<HTMLDivElement>(null);
  // From the first tap until the flow ends: a second tap must not open a second dialog on top.
  const asking = useRef(false);

  // At once where less motion is asked for. Optional: jsdom has no scrollIntoView.
  useEffect(() => {
    if (refusals === 0) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    card.current?.scrollIntoView?.({ block: "nearest", behavior: still ? "auto" : "smooth" });
  }, [refusals]);

  const ask = async (): Promise<boolean> => {
    if (!(await requestWriteAccess())) {
      setRefused(true);
      setRefusals((count) => count + 1);
      return false;
    }
    try {
      await allowWrite.mutateAsync();
    } catch {
      return false; // the mutation cache's own handler already showed a toast
    }
    return true;
  };

  const ensure = async (): Promise<boolean> => {
    if (canWrite === false) {
      if (asking.current) return false;
      asking.current = true;
      try {
        if (!(await ask())) return false;
      } finally {
        asking.current = false;
      }
    }
    setRefused(false);
    return true;
  };

  return { ensure, refused, pending: allowWrite.isPending, card };
}
