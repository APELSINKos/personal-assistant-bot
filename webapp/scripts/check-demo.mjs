// Checks the built demo before it is published (spec §7.3): node scripts/check-demo.mjs <folder>.
// The site is public, and so are the logs of Actions: the check names the file and the rule it
// broke and never prints what it found, since a check that printed a stray address would publish it.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, sep } from "node:path";

/** The only hosts the demo may name: its own site, the app's links and credits, SVG's namespace. */
const HOSTS = new Set([
  "www.w3.org", "react.dev", "www.geonames.org", "telegram.org", "t.me", "open-meteo.com", "github.com",
  "creativecommons.org", "apelsinkos.github.io", "example.com",
]);
const TEXT = new Set([".html", ".js", ".mjs", ".css", ".svg", ".json", ".txt", ".xml", ".webmanifest"]);
const SCRIPTS = new Set([".js", ".mjs"]);
const COVER = new URL("../../docs/images/cover.jpg", import.meta.url);
const LIMIT = 5 * 1024 * 1024;

// An address with its scheme anywhere in a text, and one without it (//host) in an attribute or in
// CSS. Only a written-out host counts: «https://${host}» and «https://…» name none.
const ABSOLUTE = /https?:\/\/(?:[^\s/?#@"'`<>]*@)?([a-z0-9.-]*)/gi;
const ATTRIBUTE = /=\s*["']?\s*\/\/([a-z0-9.-]*)/gi;
const STYLE = /(?:url\(\s*["']?|@import\s+["'])\s*\/\/([a-z0-9.-]*)/gi;
// Services that make a host name of an IP address.
const IP_SERVICE = /(?:sslip|nip)\.io/i;
// Four numbers with nothing but other characters around them: not a part of «1.2.3.4.5».
const IPV4 = /(?:^|[^\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])/g;
// A group that looks behind: "(?<" with "=" or "!". Escaped, since no source of the webapp holds the
// two together (src/test/sourceRules.test.ts).
const LOOKBEHIND = /\(\?<[=!]/;

/** The hosts an address pattern finds that are not on the list. */
function strangers(text, pattern) {
  return [...text.matchAll(pattern)]
    .map((match) => (match[1] ?? "").replace(/\.+$/, "").toLowerCase())
    .filter((host) => host !== "" && !HOSTS.has(host));
}

function hasIpv4(text) {
  return [...text.matchAll(IPV4)].some((match) => match.slice(1, 5).every((part) => Number(part) <= 255));
}

function decode(value) {
  return value.replace(/&(#39|#x27|apos|quot|#34|amp);/gi, (_, name) => {
    const entity = name.toLowerCase();
    if (entity === "amp") return "&";
    return entity === "quot" || entity === "#34" ? '"' : "'";
  });
}

/** What is wrong with a page's policy: it must be the first tag of <head> and refuse any connection. */
function policyProblem(html) {
  const head = /<head\b[^>]*>([\s\S]*)/i.exec(html)?.[1];
  const first = head === undefined ? "" : (/^\s*(?:<!--[\s\S]*?-->\s*)*<([^>]*)>/.exec(head)?.[1] ?? "");
  if (!/^meta\s/i.test(first) || !/\bhttp-equiv\s*=\s*["']?content-security-policy\b/i.test(first)) {
    return "the Content-Security-Policy is not the first tag of <head>";
  }
  const content = /\bcontent\s*=\s*(?:"([^"]*)"|'([^']*)')/i.exec(first);
  const directives = decode(content?.[1] ?? content?.[2] ?? "")
    .split(";")
    .map((directive) => directive.trim().replace(/\s+/g, " ").toLowerCase());
  // As browsers read a policy: the first connect-src counts, and without one default-src does.
  const connect = directives.find((directive) => directive.split(" ")[0] === "connect-src");
  return connect === "connect-src 'none'" ? null : "the Content-Security-Policy does not refuse every connection";
}

function check(folder) {
  const problems = new Set();
  const names = readdirSync(folder, { recursive: true })
    .map(String)
    .filter((name) => statSync(join(folder, name)).isFile());
  let total = 0;
  for (const name of names) {
    const shown = name.split(sep).join("/");
    const kind = extname(name).toLowerCase();
    const bytes = readFileSync(join(folder, name));
    total += bytes.length;
    const raw = bytes.toString("latin1");
    if (IP_SERVICE.test(raw)) problems.add(`${shown}: an IP-address service (sslip.io, nip.io)`);
    if (hasIpv4(raw)) problems.add(`${shown}: an IPv4 address`);
    if (kind === ".map") problems.add(`${shown}: a source map`);
    if (!TEXT.has(kind)) continue;
    const text = bytes.toString("utf8");
    const markup = kind === ".html" || kind === ".svg";
    const found = [
      ...strangers(text, ABSOLUTE),
      ...(markup ? strangers(text, ATTRIBUTE) : []),
      ...(markup || kind === ".css" ? strangers(text, STYLE) : []),
    ];
    if (found.length > 0) problems.add(`${shown}: an address whose host is not on the list`);
    if (SCRIPTS.has(kind) && LOOKBEHIND.test(text)) {
      problems.add(`${shown}: a lookbehind in a regular expression`);
    }
    if (kind === ".html") {
      const policy = policyProblem(text);
      if (policy) problems.add(`${shown}: ${policy}`);
      if (text.includes("telegram-web-app.js")) problems.add(`${shown}: Telegram's script`);
    }
  }
  const og = names.includes("og.jpg") ? readFileSync(join(folder, "og.jpg")) : null;
  if (!og) problems.add("og.jpg: missing");
  else if (!og.equals(readFileSync(COVER))) problems.add("og.jpg: not docs/images/cover.jpg");
  if (total > LIMIT) problems.add(`the demo is over 5 MB: ${(total / 1024 / 1024).toFixed(1)} MB`);
  return { problems: [...problems], files: names.length, total };
}

const folder = process.argv[2];
if (!folder || !statSync(folder, { throwIfNoEntry: false })?.isDirectory()) {
  console.error("Usage: node scripts/check-demo.mjs <the folder of the built demo>");
  process.exit(2);
}
const { problems, files, total } = check(folder);
for (const problem of problems) console.error(`check-demo: ${problem}`);
if (problems.length > 0) {
  console.error(`check-demo: ${problems.length} problem(s), the demo must not be published`);
  process.exit(1);
}
console.log(`check-demo: ${files} files, ${Math.round(total / 1024)} KB, all clear`);
