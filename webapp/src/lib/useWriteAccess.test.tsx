import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { createQueryClient } from "../api/queries";
import type { TgWebApp } from "../telegram";
import { installTelegram } from "../test/fakeTelegram";
import { me } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { useWriteAccess } from "./useWriteAccess";

type Dialog = NonNullable<TgWebApp["requestWriteAccess"]>;

const SERVER_FAILURE = { status: 500, body: { status: 500, code: "generic", title: "x" } };

/** Telegram's dialog that stays open until the test answers it. */
function openDialog() {
  const waiting: ((allowed: boolean) => void)[] = [];
  const requestWriteAccess = vi.fn<Dialog>((callback) => {
    if (callback) waiting.push(callback);
  });
  return { requestWriteAccess, answer: (allowed: boolean) => act(() => waiting.shift()?.(allowed)) };
}

const declined = () => vi.fn<Dialog>((callback) => callback?.(false));

function setup(
  canWrite: boolean | undefined,
  { telegram = {}, routes = {} }: { telegram?: Partial<TgWebApp>; routes?: Record<string, unknown> } = {},
) {
  const app = installTelegram(telegram);
  const { calls } = mockApi({ "POST /me/write-access": { ...me, can_write: true }, ...routes });
  const client = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(({ allowed }) => useWriteAccess(allowed), { wrapper, initialProps: { allowed: canWrite } });
  return { app, calls, hook };
}

type Hook = ReturnType<typeof setup>["hook"];
interface Outcome {
  answer?: boolean;
}

/** Starts `ensure()`; `answer` is filled in when the flow has ended. */
function start(hook: Hook): Outcome {
  const outcome: Outcome = {};
  act(() => {
    void hook.result.current.ensure().then((answer) => {
      outcome.answer = answer;
    });
  });
  return outcome;
}

/** Waits for the flow's answer, then lets the renders it caused land. */
async function answered(outcome: Outcome) {
  await waitFor(() => expect(outcome.answer).toBeDefined());
  await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
}

describe("useWriteAccess", () => {
  it("lets the action through without asking while the profile is not loaded", async () => {
    const { app, calls, hook } = setup(undefined);
    const outcome = start(hook);
    await answered(outcome);
    expect(outcome.answer).toBe(true);
    expect(app.requestWriteAccess).not.toHaveBeenCalled();
    expect(calls).toEqual([]);
    expect(hook.result.current.refused).toBe(false);
  });

  it("lets the action through without asking when the permission is there", async () => {
    const { app, calls, hook } = setup(true);
    const outcome = start(hook);
    await answered(outcome);
    expect(outcome.answer).toBe(true);
    expect(app.requestWriteAccess).not.toHaveBeenCalled();
    expect(calls).toEqual([]);
  });

  it("asks Telegram, then records the answer on the server", async () => {
    const { app, calls, hook } = setup(false);
    const outcome = start(hook);
    await answered(outcome);
    expect(outcome.answer).toBe(true);
    expect(app.requestWriteAccess).toHaveBeenCalledTimes(1);
    expect(calls).toEqual([{ method: "POST", path: "/me/write-access", body: undefined }]);
    expect(hook.result.current.refused).toBe(false);
  });

  it("is pending while the server records the answer", async () => {
    let release: (reply: unknown) => void = () => undefined;
    const held = () => new Promise((resolve) => { release = resolve; });
    const { hook } = setup(false, { routes: { "POST /me/write-access": held } });
    const outcome = start(hook);
    await waitFor(() => expect(hook.result.current.pending).toBe(true));
    act(() => release({ body: { ...me, can_write: true } }));
    await answered(outcome);
    expect(outcome.answer).toBe(true);
    expect(hook.result.current.pending).toBe(false);
  });

  it("says no and shows the refusal when the user declines in Telegram", async () => {
    const { calls, hook } = setup(false, { telegram: { requestWriteAccess: declined() } });
    const outcome = start(hook);
    await answered(outcome);
    expect(outcome.answer).toBe(false);
    expect(hook.result.current.refused).toBe(true);
    expect(calls).toEqual([]);
  });

  it("says no, without a refusal, when the server could not record the answer", async () => {
    const { hook } = setup(false, { routes: { "POST /me/write-access": SERVER_FAILURE } });
    const outcome = start(hook);
    await answered(outcome);
    expect(outcome.answer).toBe(false);
    expect(hook.result.current.refused).toBe(false);
  });

  it("takes the refusal back as soon as an action goes through", async () => {
    const { hook } = setup(false, { telegram: { requestWriteAccess: declined() } });
    await answered(start(hook));
    expect(hook.result.current.refused).toBe(true);
    hook.rerender({ allowed: true }); // the permission came by another route
    const outcome = start(hook);
    await answered(outcome);
    expect(outcome.answer).toBe(true);
    expect(hook.result.current.refused).toBe(false);
  });

  it("says no at once to a second call while the first one's prompt is open", async () => {
    const { requestWriteAccess, answer } = openDialog();
    const { hook } = setup(false, { telegram: { requestWriteAccess } });
    const first = start(hook);
    expect(requestWriteAccess).toHaveBeenCalledTimes(1);
    const second = start(hook);
    await answered(second);
    expect(second.answer).toBe(false);
    expect(requestWriteAccess).toHaveBeenCalledTimes(1);
    expect(first.answer).toBeUndefined();
    answer(true);
    await answered(first);
    expect(first.answer).toBe(true);
  });

  it("can ask again once the previous question is over", async () => {
    const dialog = declined();
    const { hook } = setup(false, { telegram: { requestWriteAccess: dialog } });
    await answered(start(hook));
    await answered(start(hook));
    expect(dialog).toHaveBeenCalledTimes(2);
  });

  it("can ask again after the server failed to record the answer", async () => {
    const { app, hook } = setup(false, { routes: { "POST /me/write-access": SERVER_FAILURE } });
    await answered(start(hook));
    await answered(start(hook));
    expect(app.requestWriteAccess).toHaveBeenCalledTimes(2);
  });
});
