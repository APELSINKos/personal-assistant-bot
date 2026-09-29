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
let items: ToastItem[] = [];
let nextId = 1;

function emit(): void {
  for (const listener of listeners) listener();
}

export function dismiss(id: number): void {
  items = items.filter((item) => item.id !== id);
  emit();
}

export function toast(input: ToastInput): void {
  const item = { ...input, id: nextId };
  nextId += 1;
  items = [...items, item].slice(-3);
  emit();
  setTimeout(() => dismiss(item.id), LIFETIME_MS);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useToasts(): ToastItem[] {
  return useSyncExternalStore(subscribe, () => items);
}
