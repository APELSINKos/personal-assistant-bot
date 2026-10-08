import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { act } from "@testing-library/react";

/** A refusal the app does not try again: a refresh answered with it fails at once. */
export const RATE_LIMITED = { status: 429, body: { status: 429, code: "rate_limited", title: "Too many requests" } };

/** Asks for a query again, as a return to the app or a pull does, and lets the screen take the outcome. */
export async function refresh(client: QueryClient, queryKey: QueryKey): Promise<void> {
  await act(async () => {
    await client.refetchQueries({ queryKey });
    await new Promise((resolve) => setTimeout(resolve, 0)); // observers hear of it a tick later
  });
}
