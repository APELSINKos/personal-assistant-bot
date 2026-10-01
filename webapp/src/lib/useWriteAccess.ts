import { useRef, useState } from "react";
import { useAllowWrite } from "../api/queries";
import { requestWriteAccess } from "../telegram";

/**
 * A reminder or a lesson alert is a message from the bot, and the bot may write to the user only
 * after Telegram's "allow the bot to message you" dialog and the server's record of the answer.
 * `ensure()` runs that when the profile says the permission is missing and resolves to whether the
 * action that needs it may go on; while the profile is not loaded (`canWrite` is undefined) the
 * action goes on, and the server has the last word. `refused` is set by a refusal and cleared by
 * the next `ensure()` that lets the action go on, whichever way the permission came.
 */
export function useWriteAccess(canWrite: boolean | undefined) {
  const allowWrite = useAllowWrite();
  const [refused, setRefused] = useState(false);
  // From the first tap until the flow ends: a second tap must not open a second dialog on top.
  const asking = useRef(false);

  const ask = async (): Promise<boolean> => {
    if (!(await requestWriteAccess())) {
      setRefused(true);
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

  return { ensure, refused, pending: allowWrite.isPending };
}
