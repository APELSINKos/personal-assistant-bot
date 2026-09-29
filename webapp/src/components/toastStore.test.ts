import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { clearToasts, toast, useToasts } from "./toastStore";

describe("toastStore", () => {
  it("clears toasts and cancels their pending dismiss timers", () => {
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useToasts());
      act(() => {
        toast({ kind: "error", code: "not_found" });
      });
      expect(result.current).toHaveLength(1);

      act(() => {
        clearToasts();
      });
      expect(result.current).toHaveLength(0);

      // If the timer had survived clearToasts(), advancing past its lifetime would throw or
      // leave stray state; nothing should happen here.
      act(() => {
        vi.advanceTimersByTime(10_000);
      });
      expect(result.current).toHaveLength(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("cancels the pending timer itself, not just the visible list", () => {
    // A timer left running past clearToasts() would fire during a later, unrelated test and call
    // dismiss() outside any act(), producing act() warnings and cross-test state leakage — so
    // clearToasts() must call clearTimeout(), not just empty the list.
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout");
    act(() => {
      toast({ kind: "success", text: "Готово" });
    });
    clearTimeoutSpy.mockClear();

    act(() => {
      clearToasts();
    });

    expect(clearTimeoutSpy).toHaveBeenCalledTimes(1);
  });
});
