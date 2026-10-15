import { describe, expect, it } from "vitest";
import { preparedId, preparedPicture } from "./prepared";

describe("the demo's prepared messages", () => {
  it("name their picture in their id", () => {
    expect(preparedId("habit", 7, 1)).toBe("demo-habit-7-1");
    expect(preparedId("forecast", 0, 2)).toBe("demo-forecast-0-2");
    expect(preparedPicture(preparedId("habit", 7, 1))).toBe("habit");
    expect(preparedPicture(preparedId("forecast", 0, 2))).toBe("forecast");
  });

  it("show the habit card for an id they did not make", () => {
    expect(preparedPicture("demo-7-1")).toBe("habit");
    expect(preparedPicture("")).toBe("habit");
  });
});
