import { describe, expect, it } from "vitest";
import { Problem, problemReply } from "./http";
import { check, dateValue, itemId, queryInt, queryText, type Fields } from "./validate";

/** The problem+json a refused request gets. */
function refused(run: () => unknown): unknown {
  try {
    run();
  } catch (error) {
    if (error instanceof Problem) return problemReply(error).body;
    throw error;
  }
  throw new Error("Nothing was refused");
}

/** A 422 as FastAPI's validation answers it. */
function invalid(detail: string, field?: string, limit?: number) {
  return {
    type: "about:blank", title: "Invalid input", status: 422, code: "validation_error", detail,
    ...(field === undefined ? {} : { field }), ...(limit === undefined ? {} : { limit }),
  };
}

const RULE: Fields = {
  repeat: { type: "str", required: true, choices: ["daily", "weekly", "monthly"] },
  time_local: { type: "str", required: true, pattern: /^\d{2}:\d{2}$/ },
  weekdays: { type: "int", nullable: true, ge: 1, le: 127 },
};
const BODY: Fields = {
  text: { type: "str", required: true, min: 1, max: 5 },
  done: { type: "bool" },
  items: { type: "list" },
  rate: { type: "float", ge: -90, le: 90 },
  day: { type: "date", nullable: true },
  rule: { type: "model", name: "RuleIn", fields: RULE, nullable: true },
};

describe("a body checked as the API's models check it", () => {
  it("takes what fits", () => {
    expect(() => check({ text: "💪💪💪💪💪", done: true, items: ["a"], rate: 55.75, day: "2026-10-07" }, BODY)).not.toThrow();
    expect(() => check({ text: "a", day: null, rule: { repeat: "daily", time_local: "08:00", weekdays: null } }, BODY))
      .not.toThrow();
  });

  it("refuses what is not an object, a missing field and a field it does not know", () => {
    const notObject = invalid("Input should be a valid dictionary or object to extract fields from");
    expect(refused(() => check(["text"], BODY))).toEqual(notObject);
    expect(refused(() => check(undefined, BODY))).toEqual(invalid("Field required"));
    expect(refused(() => check({}, BODY))).toEqual(invalid("Field required", "text"));
    expect(refused(() => check({ text: "a", colour: "mint" }, BODY))).toEqual(
      invalid("Extra inputs are not permitted", "colour"),
    );
  });

  it("refuses a value of another type", () => {
    expect(refused(() => check({ text: 5 }, BODY))).toEqual(invalid("Input should be a valid string", "text"));
    expect(refused(() => check({ text: "a", done: "yes" }, BODY))).toEqual(
      invalid("Input should be a valid boolean", "done"),
    );
    expect(refused(() => check({ text: "a", items: "a" }, BODY))).toEqual(invalid("Input should be a valid list", "items"));
    expect(refused(() => check({ text: "a", items: ["a", 2] }, BODY))).toEqual(
      invalid("Input should be a valid string", "items.1"),
    );
    expect(refused(() => check({ text: "a", rate: "1" }, BODY))).toEqual(invalid("Input should be a valid number", "rate"));
    expect(refused(() => check({ text: null }, BODY))).toEqual(invalid("Input should be a valid string", "text"));
  });

  it("counts a text in code points and tells the limit", () => {
    expect(refused(() => check({ text: "" }, BODY))).toEqual(
      invalid("String should have at least 1 character", "text", 1),
    );
    expect(refused(() => check({ text: "💪💪💪💪💪💪" }, BODY))).toEqual(
      invalid("String should have at most 5 characters", "text", 5),
    );
    expect(refused(() => check({ text: "a", rate: 90.5 }, BODY))).toEqual(
      invalid("Input should be less than or equal to 90", "rate", 90),
    );
  });

  it("checks a date, a choice, a pattern and a model inside the body", () => {
    expect(refused(() => check({ text: "a", day: "2026-02-30" }, BODY))).toEqual(
      invalid("Input should be a valid date in the format YYYY-MM-DD", "day"),
    );
    expect(refused(() => check({ text: "a", rule: "daily" }, BODY))).toEqual(
      invalid("Input should be a valid dictionary or instance of RuleIn", "rule"),
    );
    expect(refused(() => check({ text: "a", rule: { repeat: "yearly", time_local: "08:00" } }, BODY))).toEqual(
      invalid("Input should be 'daily', 'weekly' or 'monthly'", "rule.repeat"),
    );
    expect(refused(() => check({ text: "a", rule: { repeat: "daily", time_local: "8:00" } }, BODY))).toEqual(
      invalid("String should match pattern '^\\d{2}:\\d{2}$'", "rule.time_local"),
    );
    expect(refused(() => check({ text: "a", rule: { repeat: "weekly", time_local: "08:00", weekdays: 0 } }, BODY)))
      .toEqual(invalid("Input should be greater than or equal to 1", "rule.weekdays", 1));
    expect(refused(() => check({ text: "a", rule: { repeat: "daily", time_local: "08:00", at: 1 } }, BODY)))
      .toEqual(invalid("Extra inputs are not permitted", "rule.at"));
  });
});

describe("the parameters of a path and a query", () => {
  it("take an id of a record as SQLite keeps it", () => {
    expect(itemId("7", "note_id")).toBe(7);
    expect(refused(() => itemId("x", "note_id"))).toEqual(
      invalid("Input should be a valid integer, unable to parse string as an integer", "note_id"),
    );
    expect(refused(() => itemId("0", "note_id"))).toEqual(
      invalid("Input should be greater than or equal to 1", "note_id", 1),
    );
    // The limit comes as the app's JSON.parse reads the server's: as the nearest number.
    expect(refused(() => itemId("9223372036854775808", "note_id"))).toEqual(
      invalid("Input should be less than or equal to 9223372036854775807", "note_id", Number(2n ** 63n - 1n)),
    );
  });

  it("take a date", () => {
    expect(dateValue("2026-10-07", "day")).toBe("2026-10-07");
    expect(refused(() => dateValue("2026-13-01", "day"))).toEqual(
      invalid("Input should be a valid date in the format YYYY-MM-DD", "day"),
    );
  });

  it("take a number and a text of a query, with their bounds", () => {
    const query = new URLSearchParams("city=3&q=Мо&bad=x&minus=-1");
    expect(queryInt(query, "city", { ge: 0 })).toBe(3);
    expect(queryInt(query, "none", { ge: 0 })).toBeNull();
    expect(refused(() => queryInt(query, "bad", { ge: 0 }))).toEqual(
      invalid("Input should be a valid integer, unable to parse string as an integer", "bad"),
    );
    expect(refused(() => queryInt(query, "minus", { ge: 0 }))).toEqual(
      invalid("Input should be greater than or equal to 0", "minus", 0),
    );
    expect(queryText(query, "q", { required: true, min: 2, max: 50 })).toBe("Мо");
    expect(queryText(query, "none", {})).toBeNull();
    expect(refused(() => queryText(query, "none", { required: true }))).toEqual(invalid("Field required", "none"));
    expect(refused(() => queryText(new URLSearchParams("q=М"), "q", { min: 2 }))).toEqual(
      invalid("String should have at least 2 characters", "q", 2),
    );
  });
});
