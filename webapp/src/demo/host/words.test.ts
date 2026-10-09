import { describe, expect, it } from "vitest";
import { BOT_CHAT_URL } from "../../lib/links";
import { REPO_URL } from "../../screens/More";
import { LINKS } from "./words";

describe("the host page's links", () => {
  it("lead where the app's own do", () => {
    expect(LINKS.bot).toBe(BOT_CHAT_URL);
    expect(LINKS.source).toBe(REPO_URL);
  });
});
