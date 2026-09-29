import { useSyncExternalStore } from "react";

export interface ToastInput {
  kind: "error" | "success";
  code?: string;
  text?: string;
}

export interface ToastItem extends ToastInput {
  id: number;
}

const LIFETIME_MS = 3500;
const listeners = new Set<() => void>();
const timers = new Map<number, ReturnType<typeof setTimeout>>();
let items: ToastItem[] = [];
let nextId = 1;

function emit(): void {
  for (const listener of listeners) listener();
}

export function dismiss(id: number): void {
  const timer = timers.get(id);
  if (timer !== undefined) clearTimeout(timer);
  timers.delete(id);
  items = items.filter((item) => item.id !== id);
  emit();
}

export function toast(input: ToastInput): void {
  const item = { ...input, id: nextId };
  nextId += 1;
  items = [...items, item].slice(-3);
  emit();
  timers.set(item.id, setTimeout(() => dismiss(item.id), LIFETIME_MS));
}

/** Clears all toasts and their pending timers — call between tests so state doesn't leak. */
export function clearToasts(): void {
  for (const timer of timers.values()) clearTimeout(timer);
  timers.clear();
  items = [];
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useToasts(): ToastItem[] {
  return useSyncExternalStore(subscribe, () => items);
}
