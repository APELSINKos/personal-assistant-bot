/**
 * The checks of a request before the routers see it, as the API's pydantic models (schemas.py)
 * and FastAPI's parameters make them: a body of known fields only, each of its type and within
 * its bounds, lengths in code points. A refusal is FastAPI's 422 as errors.py words it: the first
 * error's message, its field and its limit.
 */
import { codePoints } from "../../lib/format";
import { invalidInput } from "./http";
import { realDay } from "./time";

interface Common {
  /** The field must be there; null is no value for it unless it may be null. */
  required?: boolean;
  nullable?: boolean;
}

export type Rule = Common & (
  | { type: "str"; min?: number; max?: number; pattern?: RegExp; choices?: readonly string[] }
  | { type: "bool" }
  | { type: "int"; ge?: number; le?: number | bigint; choices?: readonly number[] }
  | { type: "float"; ge?: number; le?: number }
  | { type: "date" }
  | { type: "list" }
  | { type: "model"; name: string; fields: Fields }
);

/** A model's fields, in its order. */
export type Fields = Record<string, Rule>;

/** SQLite's largest INTEGER: the bound of every id the API takes. */
export const ID_MAX = 2n ** 63n - 1n;

const plural = (count: number) => (count === 1 ? "" : "s");

function refuse(detail: string, field?: string, limit?: number): never {
  throw invalidInput({ detail, field: field || undefined, limit });
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** pydantic's words for a choice: «'auto', 'ru' or 'en'». */
function choiceList(choices: readonly (string | number)[]): string {
  const shown = choices.map((choice) => (typeof choice === "string" ? `'${choice}'` : String(choice)));
  return shown.length > 1 ? `${shown.slice(0, -1).join(", ")} or ${shown.at(-1)}` : (shown[0] ?? "");
}

/** A number within its bounds; a bound as large as SQLite's ids comes as a bigint, exact. */
function checkNumber(value: number, ge: number | undefined, le: number | bigint | undefined, field: string): void {
  if (ge !== undefined && value < ge) refuse(`Input should be greater than or equal to ${ge}`, field, ge);
  const over = typeof le === "bigint" ? BigInt(value) > le : le !== undefined && value > le;
  if (over) refuse(`Input should be less than or equal to ${le}`, field, Number(le));
}

function checkText(value: string, rule: { min?: number; max?: number; pattern?: RegExp }, field: string): void {
  const length = codePoints(value);
  if (rule.min !== undefined && length < rule.min) {
    refuse(`String should have at least ${rule.min} character${plural(rule.min)}`, field, rule.min);
  }
  if (rule.max !== undefined && length > rule.max) {
    refuse(`String should have at most ${rule.max} character${plural(rule.max)}`, field, rule.max);
  }
  if (rule.pattern && !rule.pattern.test(value)) refuse(`String should match pattern '${rule.pattern.source}'`, field);
}

/** A Literal of the models: one of its values and nothing else, whatever the type. */
function checkChoice(value: unknown, choices: readonly (string | number)[], field: string): void {
  if (!choices.includes(value as string | number)) refuse(`Input should be ${choiceList(choices)}`, field);
}

function checkValue(value: unknown, rule: Rule, field: string): void {
  switch (rule.type) {
    case "str":
      if (rule.choices) return checkChoice(value, rule.choices, field);
      if (typeof value !== "string") return refuse("Input should be a valid string", field);
      return checkText(value, rule, field);
    case "bool":
      if (typeof value !== "boolean") refuse("Input should be a valid boolean", field);
      return;
    case "int":
      if (rule.choices) return checkChoice(value, rule.choices, field);
      if (typeof value !== "number" || !Number.isFinite(value)) return refuse("Input should be a valid integer", field);
      if (!Number.isInteger(value)) return refuse("Input should be a valid integer, got a number with a fractional part", field);
      return checkNumber(value, rule.ge, rule.le, field);
    case "float":
      if (typeof value !== "number" || !Number.isFinite(value)) return refuse("Input should be a valid number", field);
      return checkNumber(value, rule.ge, rule.le, field);
    case "date":
      if (typeof value !== "string" || !realDay(value)) refuse("Input should be a valid date in the format YYYY-MM-DD", field);
      return;
    case "list":
      if (!Array.isArray(value)) return refuse("Input should be a valid list", field);
      value.forEach((item, index) => {
        if (typeof item !== "string") refuse("Input should be a valid string", `${field}.${index}`);
      });
      return;
    case "model":
      if (!isObject(value)) return refuse(`Input should be a valid dictionary or instance of ${rule.name}`, field);
      return check(value, rule.fields, `${field}.`);
  }
}

/**
 * Checks a body against a model's fields; the first error refuses the request. Each field in the
 * model's order, then the fields the model does not know.
 */
export function check(body: unknown, fields: Fields, prefix = ""): void {
  if (body === undefined && !prefix) refuse("Field required");
  if (!isObject(body)) return refuse("Input should be a valid dictionary or object to extract fields from", prefix.slice(0, -1));
  for (const [name, rule] of Object.entries(fields)) {
    const value = body[name];
    if (value === undefined) {
      if (rule.required) refuse("Field required", prefix + name);
      continue;
    }
    if (value === null && rule.nullable) continue;
    checkValue(value, rule, prefix + name);
  }
  for (const name of Object.keys(body)) {
    if (!Object.hasOwn(fields, name)) refuse("Extra inputs are not permitted", prefix + name);
  }
}

/** A whole number of a path or a query, as FastAPI parses one. */
function wholeNumber(raw: string, field: string): bigint {
  if (!/^[+-]?\d+$/.test(raw.trim())) refuse("Input should be a valid integer, unable to parse string as an integer", field);
  return BigInt(raw.trim());
}

/** An id in a path (deps.ItemId): a whole number from 1 to SQLite's largest. */
export function itemId(raw: string, field: string): number {
  const value = wholeNumber(raw, field);
  if (value < 1n) refuse("Input should be greater than or equal to 1", field, 1);
  if (value > ID_MAX) refuse(`Input should be less than or equal to ${ID_MAX}`, field, Number(ID_MAX));
  return Number(value);
}

/** A date of a path or a query. */
export function dateValue(raw: string, field: string): string {
  if (!realDay(raw)) refuse("Input should be a valid date in the format YYYY-MM-DD", field);
  return raw;
}

/** A whole number of the query, null without it. */
export function queryInt(query: URLSearchParams, name: string, bounds: { ge?: number; le?: bigint }): number | null {
  const raw = query.get(name);
  if (raw === null) return null;
  const value = wholeNumber(raw, name);
  if (bounds.ge !== undefined && value < BigInt(bounds.ge)) {
    refuse(`Input should be greater than or equal to ${bounds.ge}`, name, bounds.ge);
  }
  if (bounds.le !== undefined && value > bounds.le) {
    refuse(`Input should be less than or equal to ${bounds.le}`, name, Number(bounds.le));
  }
  return Number(value);
}

/** A text of the query, null without it. */
export function queryText(
  query: URLSearchParams,
  name: string,
  rule: { required?: boolean; min?: number; max?: number; pattern?: RegExp },
): string | null {
  const value = query.get(name);
  if (value === null) {
    if (rule.required) refuse("Field required", name);
    return null;
  }
  checkText(value, rule, name);
  return value;
}
