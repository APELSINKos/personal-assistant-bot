import { vi } from "vitest";
import type { Lang } from "../../i18n";
import type { ApiReply, ApiRequest, DemoFrame, DemoHost, MainButtonState } from "./contract";

function notFound(): ApiReply {
  return { status: 404, body: { status: 404, code: "not_found", title: "Not Found" }, headers: {} };
}

/**
 * A host page for the bridges' tests: every call recorded, the API's answers given by the test, and
 * the frame that connected kept, so that a test can press the host's buttons. The visitor speaks
 * Russian unless told otherwise.
 */
export function testHost(answer: (request: ApiRequest) => ApiReply = notFound, language: Lang = "ru") {
  let frame: DemoFrame | null = null;
  const host = {
    language,
    user: { id: 1, first_name: language === "ru" ? "Саша" : "Alex", language_code: language },
    clockOffset: null,
    scheme: vi.fn<() => "dark" | "light">(() => "dark"),
    api: vi.fn(answer),
    connect: vi.fn((next: DemoFrame) => {
      frame = next;
    }),
    ready: vi.fn(),
    paint: vi.fn<(part: "header" | "background" | "bottom", color: string) => void>(),
    backButton: vi.fn<(visible: boolean) => void>(),
    mainButton: vi.fn<(state: MainButtonState) => void>(),
    closingConfirmation: vi.fn<(enabled: boolean) => void>(),
    confirm: vi.fn<(message: string) => Promise<boolean>>(async () => true),
    writeAccess: vi.fn<() => Promise<boolean>>(async () => true),
    share: vi.fn<(preparedId: string) => Promise<boolean>>(async () => true),
  } satisfies DemoHost;
  const connected = (): DemoFrame => {
    if (!frame) throw new Error("No frame has connected to the host");
    return frame;
  };
  return { host, frame: connected };
}
