import { describe, expect, it } from "vitest";
import { hostAddress, parentHost } from "./frame";
import { testHost } from "./testHost";

describe("the frame's way to the host page", () => {
  it("finds the host on the parent window", () => {
    const { host } = testHost();
    expect(parentHost({ parent: { __demoHost: host } as unknown as Window })).toBe(host);
  });

  it("finds none on a page of its own", () => {
    expect(parentHost({ parent: {} as Window })).toBeNull();
    expect(parentHost()).toBeNull();
  });

  it("finds none behind a parent page of another site", () => {
    // A page of another origin answers any look inside it with a SecurityError.
    const foreign = new Proxy({}, {
      get: () => {
        throw new DOMException("Blocked a frame from accessing a cross-origin frame.", "SecurityError");
      },
    });
    expect(parentHost({ parent: foreign as Window })).toBeNull();
  });

  it("sends a frame without its host to the host page, on the same screen", () => {
    expect(hostAddress("#/weather")).toBe("./#/weather");
    expect(hostAddress("#/notes/12")).toBe("./#/notes/12");
    expect(hostAddress("")).toBe("./#/");
    expect(hostAddress("#tgWebAppData=x")).toBe("./#/");
  });
});
