// The rule «every change of the API changes src/demo/api too» as a check (spec §18): each call of
// api() in the app's sources — its path and method — has a route in the demo's API, and the demo
// serves nothing the app does not call. The app's files are read as text. A path may reach api()
// through a function that takes it as an argument (useShareCard, useOptimisticRemove): then the
// paths come from where that function is called, with the method of its api().
import { describe, expect, it } from "vitest";
import { ROUTES } from ".";

/** The app's files as text, by their path from the webapp's folder: "/src/api/queries.ts". */
const APP: Record<string, string> = import.meta.glob<string>(
  ["/src/**/*.{ts,tsx}", "!/src/**/*.test.{ts,tsx}", "!/src/demo/**", "!/src/test/**"],
  { query: "?raw", import: "default", eager: true },
);

/** A string or a template literal: where it stands, and its text as written, ${…} included. */
interface Literal {
  start: number;
  text: string;
}

/** A call of api(): where its "(" is, its method, and the literals of its path. */
interface Call {
  open: number;
  method: string;
  paths: Literal[];
}

/** Where a literal that starts at `start` ends, after its closing quote. */
function literalEnd(source: string, start: number): number {
  const quote = source[start];
  let index = start + 1;
  while (index < source.length) {
    const char = source[index];
    if (char === "\\") index += 2;
    else if (char === quote) return index + 1;
    else if (quote === "`" && char === "$" && source[index + 1] === "{") index = closing(source, index + 1) + 1;
    else index += 1;
  }
  return index;
}

/** The code with its comments blanked out: every place stays where it was. */
function uncommented(source: string): string {
  let out = "";
  let index = 0;
  while (index < source.length) {
    const char = source[index] ?? "";
    let end = index + 1;
    if (char === '"' || char === "'" || char === "`") {
      end = literalEnd(source, index);
      out += source.slice(index, end);
    } else if (source.startsWith("//", index) || source.startsWith("/*", index)) {
      const block = source.startsWith("/*", index);
      const stop = block ? source.indexOf("*/", index) + 2 : source.indexOf("\n", index);
      end = stop < (block ? 2 : 0) ? source.length : stop;
      out += source.slice(index, end).replace(/[^\n]/g, " ");
    } else {
      out += char;
    }
    index = end;
  }
  return out;
}

const PAIRS: Record<string, string> = { "(": ")", "[": "]", "{": "}", "<": ">" };

/** The index of the bracket that closes the one at `open`, past literals and nested brackets. */
function closing(source: string, open: number): number {
  const left = source[open] ?? "";
  const right = PAIRS[left];
  let depth = 0;
  for (let index = open; index < source.length;) {
    const char = source[index];
    if (char === '"' || char === "'" || char === "`") {
      index = literalEnd(source, index);
      continue;
    }
    if (char === left) depth += 1;
    else if (char === right && (depth -= 1) === 0) return index;
    index += 1;
  }
  throw new Error(`Nothing closes the ${left} at ${open}`);
}

/** The literals between two places of the code. */
function literals(source: string, from: number, to: number): Literal[] {
  const found: Literal[] = [];
  for (let index = from; index < to;) {
    const char = source[index];
    if (char === '"' || char === "'" || char === "`") {
      const end = literalEnd(source, index);
      found.push({ start: index, text: source.slice(index + 1, end - 1) });
      index = end;
    } else {
      index += 1;
    }
  }
  return found;
}

/** The arguments of the call whose "(" is at `open`, as their spans. */
function argumentsOf(source: string, open: number): [number, number][] {
  const close = closing(source, open);
  const spans: [number, number][] = [];
  let start = open + 1;
  let depth = 0;
  for (let index = start; index < close;) {
    const char = source[index] ?? "";
    if (char === '"' || char === "'" || char === "`") {
      index = literalEnd(source, index);
      continue;
    }
    if ("([{".includes(char)) depth += 1;
    else if (")]}".includes(char)) depth -= 1;
    else if (char === "," && depth === 0) {
      spans.push([start, index]);
      start = index + 1;
    }
    index += 1;
  }
  if (source.slice(start, close).trim()) spans.push([start, close]);
  return spans;
}

/** The "(" of a call of `name` that ends at `at`, past its type arguments — api<Habit[]>(…); null for no call. */
function callOpen(source: string, at: number): number | null {
  let index = at;
  while (source[index] === " ") index += 1;
  if (source[index] === "<") index = closing(source, index) + 1;
  return source[index] === "(" ? index : null;
}

const isPath = (literal: Literal) => /^\/[a-z]/.test(literal.text);

/** A path as the routes write theirs: its parameters as {}, without its query. */
function shape(path: string): string {
  return path.replace(/\$\{[^}]*\}|\{[^}]*\}/g, "{}").split("?")[0] ?? "";
}

/** The calls of `name` in the code: where each "(" stands. */
function callsOf(source: string, name: string): number[] {
  return [...source.matchAll(new RegExp(`\\b${name}\\b`, "g"))].flatMap((found) => {
    const at = found.index ?? 0;
    if (/\bfunction\s+$/.test(source.slice(0, at))) return [];
    const open = callOpen(source, at + name.length);
    return open === null ? [] : [open];
  });
}

/** The calls of api() in the code. */
function apiCalls(source: string): Call[] {
  return callsOf(source, "api").map((open) => {
    const [path, options] = argumentsOf(source, open);
    const method = options ? /\bmethod:\s*"(\w+)"/.exec(source.slice(...options))?.[1] : undefined;
    return { open, method: method ?? "GET", paths: path ? literals(source, ...path).filter(isPath) : [] };
  });
}

/** The innermost function declared around a place of the code. */
function enclosing(source: string, at: number): string | undefined {
  const around = [...source.matchAll(/\bfunction\s+(\w+)\s*(?:<[^(]*>)?\s*\(/g)].flatMap((found) => {
    const body = source.indexOf("{", closing(source, (found.index ?? 0) + found[0].length - 1));
    const end = closing(source, body);
    return body < at && at < end ? [{ name: found[1] ?? "", body }] : [];
  });
  return around.sort((a, b) => b.body - a.body)[0]?.name;
}

/** The files that call the API, those that import api from its client, without their comments. */
const CALLERS: Record<string, string> = Object.fromEntries(
  Object.entries(APP)
    .filter(([, text]) => /import\s*\{[^}]*\bapi\b[^}]*\}\s*from\s*["'][^"']*\/client["']/.test(text))
    .map(([file, text]) => [file, uncommented(text)]),
);

/** The pairs of method and path the app calls, and the paths written in the calling files that none of them placed. */
function appPairs(): { pairs: Set<string>; unplaced: string[] } {
  const pairs = new Set<string>();
  const placed = new Set<string>();
  /** The functions a path reaches api() through, with the methods of that api(). */
  const wrappers = new Map<string, Set<string>>();
  const place = (file: string, method: string, paths: Literal[]) => {
    for (const path of paths) {
      pairs.add(`${method} ${shape(path.text)}`);
      placed.add(`${file}:${path.start}`);
    }
  };
  const wrap = (name: string | undefined, method: string) => {
    if (!name) throw new Error("A path reaches api() from outside any function");
    const known = wrappers.get(name);
    wrappers.set(name, new Set([...(known ?? []), method]));
    return !known?.has(method);
  };
  for (const [file, source] of Object.entries(CALLERS)) {
    for (const call of apiCalls(source)) {
      if (call.paths.length) place(file, call.method, call.paths);
      else wrap(enclosing(source, call.open), call.method);
    }
  }
  // A wrapper's paths are where it is called; a call that passes on what it was given makes the
  // function around it a wrapper too.
  for (let changed = true; changed;) {
    changed = false;
    for (const [name, methods] of [...wrappers]) {
      if (methods.size !== 1) throw new Error(`The paths given to ${name} go to api() with ${[...methods].join(" and ")}`);
      const method = [...methods][0] ?? "GET";
      for (const [file, source] of Object.entries(CALLERS)) {
        for (const open of callsOf(source, name)) {
          const paths = literals(source, open, closing(source, open)).filter(isPath);
          if (paths.length) place(file, method, paths);
          else if (wrap(enclosing(source, open), method)) changed = true;
        }
      }
    }
  }
  const unplaced = Object.entries(CALLERS).flatMap(([file, source]) =>
    literals(source, 0, source.length)
      .filter((literal) => isPath(literal) && !placed.has(`${file}:${literal.start}`))
      .map((literal) => `${file}: ${literal.text}`));
  return { pairs, unplaced };
}

const DEMO = new Set(ROUTES.map((route) => `${route.method} ${shape(route.path)}`));

describe("the demo's API and the app's calls", () => {
  const { pairs, unplaced } = appPairs();

  it("finds the app's calls, those through a function that takes the path too", () => {
    expect(Object.keys(CALLERS).sort()).toEqual(["/src/api/money.ts", "/src/api/queries.ts"]);
    expect([...pairs]).toEqual(expect.arrayContaining([
      "GET /me", "GET /weather", "DELETE /notes/{}/items", "PUT /habits/{}/marks/{}", "POST /schedule/file",
      "DELETE /habits/{}", "POST /habits/{}/share", "POST /habits/{}/card", "POST /weather/share", "POST /weather/card",
    ]));
    // Every path written in the calling files is one of a call: no new way of passing one went unseen.
    expect(unplaced).toEqual([]);
  });

  it("has a route for each pair of method and path the app calls", () => {
    expect([...pairs].filter((pair) => !DEMO.has(pair))).toEqual([]);
  });

  it("serves nothing the app does not call", () => {
    expect([...DEMO].filter((pair) => !pairs.has(pair))).toEqual([]);
  });

  it("reads a call as the app writes it, comments aside", () => {
    const source = uncommented([
      'const a = () => api<Me>("/me");',
      'const b = (id: number) => api<void>(`/notes/${id}/items?done=true`, { method: "DELETE" });',
      '// api<Me>("/in/a/comment")',
      'const c = (city: number) => api<Forecast>(city ? `/weather?city=${city}` : "/weather");',
      "/* api<void>('/in/a/block', { method: 'PUT' }) */",
    ].join("\n"));
    expect(apiCalls(source).map((call) => [call.method, ...call.paths.map((path) => shape(path.text))])).toEqual([
      ["GET", "/me"], ["DELETE", "/notes/{}/items"], ["GET", "/weather", "/weather"],
    ]);
  });
});
