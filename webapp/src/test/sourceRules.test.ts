// The webapp's two rules for its sources (spec §4.2, §18). No lookbehind anywhere in the webapp:
// Safari before 16.4 cannot parse a file that has one, and the page stays blank. And the app's code,
// src outside src/demo, never imports the demo's, which would carry the demo into the build for
// Telegram. The files are read as text, so a lookbehind is refused wherever it stands, in a string
// for new RegExp too; scripts/check-demo.mjs looks for one again in the built demo.
import { describe, expect, it } from "vitest";
// Vite's glob leaves out the file that calls it, so this one comes in by its own import.
import thisFile from "./sourceRules.test.ts?raw";

/** Every source file of the webapp as text, by its path from the webapp's folder: "/src/lib/links.ts". */
const SOURCES: Record<string, string> = {
  ...import.meta.glob<string>(
    [
      "/*.{ts,js,mjs,html}",
      "/src/**/*.{ts,tsx,js,mjs}",
      "/demo/**/*.{ts,tsx,js,mjs,html}",
      "/scripts/**/*.{ts,js,mjs}",
    ],
    { query: "?raw", import: "default", eager: true },
  ),
  "/src/test/sourceRules.test.ts": thisFile,
};

// A group that looks behind: "(?<" with "=" or "!". The search and every probe below write the two
// apart, since this file is searched too.
const LOOKBEHIND = /\(\?<[=!]/;
const BEHIND = "(?<";

// A module's address after from, import or import(: from "…", import "…", import("…"), import(`…`).
const ADDRESS = /\b(?:from|import)\s*\(?\s*(["'`])([^"'`\n]*)\1/g;
// The demo's folder, from the webapp's.
const DEMO = /^\/src\/demo(?:\/|$)/;
const PROBE = "/src/lib/probe.ts";

/** The lines of a text that hold a lookbehind, from 1. */
function lookbehinds(text: string): number[] {
  return text.split("\n").flatMap((line, index) => (LOOKBEHIND.test(line) ? [index + 1] : []));
}

/** Where an address in the file at `path` points, from the webapp's folder; "" for a package. */
function target(path: string, address: string): string {
  if (!/^(?:\.{1,2}(?:\/|$)|\/)/.test(address)) return "";
  return new URL(address, `https://webapp.invalid${path}`).pathname;
}

/** The lines where the app's file at `path` imports the demo's code. The demo may import the app's. */
function demoImports(text: string, path: string): number[] {
  if (!path.startsWith("/src/") || DEMO.test(path)) return [];
  return [...text.matchAll(ADDRESS)]
    .filter((match) => DEMO.test(target(path, match[2] ?? "")))
    .map((match) => text.slice(0, match.index).split("\n").length);
}

/** The lines where a file at `path` loads `address` with a plain import. */
function loads(path: string, address: string): number[] {
  return demoImports(`import "${address}";`, path);
}

/** "path:line" of every line a search finds in the webapp's sources. */
function found(search: (text: string, path: string) => number[]): string[] {
  return Object.entries(SOURCES).flatMap(([path, text]) =>
    search(text, path).map((line) => `${path}:${line}`),
  );
}

describe("the webapp's sources", () => {
  it("are all read: the app and its tests, the demo and its pages, the scripts, the configs", () => {
    expect(Object.keys(SOURCES)).toEqual(
      expect.arrayContaining([
        "/index.html",
        "/vite.config.ts",
        "/vite.demo.config.ts",
        "/src/main.tsx",
        "/src/lib/links.ts",
        "/src/test/sourceRules.test.ts",
        "/src/demo/app.ts",
        "/demo/app.html",
        "/scripts/check-demo.mjs",
      ]),
    );
  });

  it("hold no lookbehind", () => {
    expect(found(lookbehinds)).toEqual([]);
  });

  it("keep the demo out of the app's code", () => {
    expect(found(demoImports)).toEqual([]);
  });
});

describe("the search for a lookbehind", () => {
  it("finds one in a literal, in a string for RegExp and in a template", () => {
    expect(lookbehinds(`export const a = /${BEHIND}=x)y/;`)).toEqual([1]);
    expect(lookbehinds(`export const a = /${BEHIND}!x)y/u;`)).toEqual([1]);
    expect(lookbehinds(`export const a = new RegExp("${BEHIND}=x)y");`)).toEqual([1]);
    expect(lookbehinds(`export const a = RegExp(\`${BEHIND}!x)y\`);`)).toEqual([1]);
    expect(lookbehinds(`// The pattern:\nconst a = "${BEHIND}=x)y";\n`)).toEqual([2]);
  });

  it("lets named groups, lookaheads and an escaped search for a lookbehind be", () => {
    expect(lookbehinds("export const a = /(?<word>x)(?=y)(?!z)/;")).toEqual([]);
    expect(lookbehinds("export const a = /\\(\\?<[=!]/;")).toEqual([]);
  });
});

describe("the search for the demo in the app's code", () => {
  it("finds every way to load a module", () => {
    const forms = [
      'import { createApi } from "ADDRESS";',
      'import type { DemoHost } from "ADDRESS";',
      "import api, {\n  type Api,\n} from 'ADDRESS';",
      'import "ADDRESS";',
      'export { createApi } from "ADDRESS";',
      'export * from "ADDRESS";',
      'const app = await import("ADDRESS");',
      "const app = await import(`ADDRESS`);",
      'type Host = typeof import("ADDRESS");',
    ];
    for (const form of forms) {
      expect(demoImports(form.replace("ADDRESS", "../demo/api"), PROBE), form).toHaveLength(1);
    }
  });

  it("finds the demo from any depth, from the webapp's root, as a folder and with a query", () => {
    const ways: [string, string][] = [
      [PROBE, "../demo/api"],
      [PROBE, "./../demo"],
      [PROBE, "/src/demo/app"],
      [PROBE, "../demo/host/host.css?inline"],
      ["/src/screens/money/probe.tsx", "../../demo/bridge/contract"],
      ["/src/probe.ts", "./demo/app"],
    ];
    for (const [path, address] of ways) expect(loads(path, address), `${path}: ${address}`).toEqual([1]);
  });

  it("lets the app load its own modules and packages, and the demo the app's", () => {
    const ways: [string, string][] = [
      [PROBE, "../api/client"],
      [PROBE, "./demo"],
      [PROBE, "../demos/x"],
      [PROBE, "react"],
      ["/src/demo/api/probe.ts", "../../api/client"],
      ["/src/demo/api/probe.ts", "../bridge/contract"],
      ["/scripts/probe.mjs", "../src/demo/app"],
    ];
    for (const [path, address] of ways) expect(loads(path, address), `${path}: ${address}`).toEqual([]);
  });

  it("names the line of the import", () => {
    const text = 'import { a } from "./a";\n\nimport { b } from "ADDRESS";\n';
    expect(demoImports(text.replace("ADDRESS", "../demo/b"), PROBE)).toEqual([3]);
  });
});
