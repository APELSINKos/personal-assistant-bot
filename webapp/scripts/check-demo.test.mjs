// The check of the built demo (spec §7.3), run as CI runs it: node scripts/check-demo.mjs <folder>.
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";

// Not new URL(…, import.meta.url): under Vitest, Vite turns that into an address of its server.
const SCRIPTS = dirname(fileURLToPath(import.meta.url));
const CHECK = join(SCRIPTS, "check-demo.mjs");
const COVER = join(SCRIPTS, "..", "..", "docs", "images", "cover.jpg");

// What a leak would carry: the check must name the file and the rule, and never this.
const SECRETS = ["secret-host", "10.20.30.40", "10-20-30-40", "2001:db8", "сервер"];

const POLICY = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
  + "font-src 'self'; connect-src 'none'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'";

/** A page as Vite writes it: the policy first in the head, its quotes as &#39;. */
function page({ policy = POLICY, head = "", body = "" } = {}) {
  const csp = `<meta http-equiv="Content-Security-Policy" content="${policy.replaceAll("'", "&#39;")}">`;
  return `<!doctype html>\n<html lang="ru">\n  <head>\n    ${csp}\n\n    <meta charset="UTF-8" />\n${head}  </head>\n`
    + `  <body>\n${body}  </body>\n</html>\n`;
}

const made = [];

/** A built demo that passes the check, with the files `changes` adds, replaces or (null) removes. */
function artifact(changes = {}) {
  const dir = mkdtempSync(join(tmpdir(), "check-demo-"));
  made.push(dir);
  const files = {
    "index.html": page({ head: '    <link rel="canonical" href="https://apelsinkos.github.io/personal-assistant-bot/" />\n' }),
    "app.html": page({ head: '    <meta name="robots" content="noindex" />\n' }),
    "assets/index.js": 'const ns="http://www.w3.org/2000/svg",bot="https://t.me/ikbo63_24_bot",v="19.3.0",'
      + 'docs="https://react.dev/errors/",r=/^https?:\\/\\/t\\.me\\//,named=/(?<word>x)(?=y)/,u=`https://${host}`,'
      + 'ical=`https://${n.slice(9)}`,hint=`https://…`,scheme="https://",port="https://t.me:443/x",'
      + 'run="1.2.3.4.5";',
    "assets/index.css": "@font-face{font-family:M;src:url(./manrope.woff2)}",
    "favicon.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>',
    "og.jpg": COVER,
    ...changes,
  };
  for (const [name, content] of Object.entries(files)) {
    if (content === null) continue;
    const path = join(dir, name);
    mkdirSync(dirname(path), { recursive: true });
    if (content === COVER) copyFileSync(COVER, path);
    else writeFileSync(path, content);
  }
  return dir;
}

function check(...args) {
  const run = spawnSync(process.execPath, [CHECK, ...args], { encoding: "utf8" });
  return { status: run.status, output: `${run.stdout}${run.stderr}` };
}

/** The check fails, says `where` and never prints what it found. */
function refuses(dir, where) {
  const { status, output } = check(dir);
  expect(status, output).toBe(1);
  expect(output).toContain(where);
  for (const secret of SECRETS) expect(output).not.toContain(secret);
}

afterEach(() => {
  for (const dir of made.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("check-demo.mjs", { timeout: 30_000 }, () => {
  it("passes a demo that keeps every rule", () => {
    const { status, output } = check(artifact());
    expect(status, output).toBe(0);
  });

  it("refuses an address whose host is not on the list", () => {
    refuses(artifact({ "assets/index.js": 'fetch("https://secret-host.example.net/api/me")' }), "assets/index.js");
    refuses(artifact({ "assets/x.json": '{"a":"http://secret-host.example.net"}' }), "assets/x.json");
    refuses(artifact({ "assets/index.js": 'location="https://github.com.secret-host.net/"' }), "assets/index.js");
    // A placeholder names no host only when it is the whole host.
    refuses(artifact({ "assets/index.js": "u=`https://${a}.secret-host.example.net/`" }), "assets/index.js");
    // A backslash ends the host of an https address, as a slash does, so this one is not github.com's.
    const backslash = '<a href="https://secret-host.example.net\\@github.com/">a</a>\n';
    refuses(artifact({ "index.html": page({ body: backslash }) }), "index.html");
  });

  it("refuses a bracketed IPv6 host", () => {
    refuses(artifact({ "assets/index.js": 'fetch("https://[2001:db8::7]/api/me")' }), "assets/index.js");
    refuses(artifact({ "assets/index.js": 'fetch("https://[2001:db8::7]:8443/api/me")' }), "assets/index.js");
    refuses(artifact({ "index.html": page({ body: '<img src="//[2001:db8::7]/a.png">\n' }) }), "index.html");
  });

  it("refuses a host outside ASCII", () => {
    refuses(artifact({ "assets/index.js": 'fetch("https://сервер.рф/api/me")' }), "assets/index.js");
    refuses(artifact({ "assets/index.css": "a{background:url(//сервер.рф/a.png)}" }), "assets/index.css");
  });

  it("refuses an address without its scheme in an attribute or a style sheet", () => {
    refuses(artifact({ "index.html": page({ body: '<img src="//secret-host.example.net/a.png">\n' }) }), "index.html");
    refuses(artifact({ "assets/index.css": "a{background:url(//secret-host.example.net/a.png)}" }), "assets/index.css");
    refuses(artifact({ "assets/index.css": '@import "//secret-host.example.net/a.css";' }), "assets/index.css");
  });

  it("refuses an IP-address service and an IPv4 address anywhere", () => {
    refuses(artifact({ "assets/index.js": 'const a="10-20-30-40.sslip.io"' }), "assets/index.js");
    refuses(artifact({ "assets/index.js": 'const a="10-20-30-40.NIP.IO"' }), "assets/index.js");
    refuses(artifact({ "assets/index.css": "/* 10.20.30.40 */" }), "assets/index.css");
    refuses(artifact({ "assets/index.css": "/* at 10.20.30.40. */" }), "assets/index.css");
    refuses(artifact({ "assets/font.woff2": Buffer.from("\u0000\u0001 10.20.30.40\u0000") }), "assets/font.woff2");
  });

  it("refuses a source map", () => {
    refuses(artifact({ "assets/index.js.map": "{}" }), "assets/index.js.map");
  });

  it("refuses a page without the policy first in its head, or one that lets it connect", () => {
    const late = '<!doctype html>\n<html>\n  <head>\n    <meta charset="UTF-8" />\n'
      + `    <meta http-equiv="Content-Security-Policy" content="${POLICY}">\n  </head>\n  <body></body>\n</html>\n`;
    refuses(artifact({ "app.html": late }), "app.html");
    refuses(artifact({ "app.html": page().replace(/<meta http-equiv[^>]*>/, "") }), "app.html");
    // A browser ignores a report-only policy in <meta>: the page would have none.
    const reportOnly = page().replace("Content-Security-Policy", "Content-Security-Policy-Report-Only");
    refuses(artifact({ "app.html": reportOnly }), "app.html");
    refuses(artifact({ "index.html": page({ policy: POLICY.replace("connect-src 'none'", "connect-src 'self'") }) }), "index.html");
    refuses(artifact({ "index.html": page({ policy: POLICY.replace("connect-src 'none'", "connect-src 'none' https:") }) }), "index.html");
  });

  it("refuses Telegram's script", () => {
    const script = '    <script src="https://telegram.org/js/telegram-web-app.js"></script>\n';
    refuses(artifact({ "index.html": page({ head: script }) }), "index.html");
  });

  it("refuses a lookbehind in a script", () => {
    // "(?<" apart from "=" and "!": no source of the webapp holds the two together, this one included.
    const behind = "(?<";
    refuses(artifact({ "assets/index.js": `const a=new RegExp("${behind}=x)y")` }), "assets/index.js");
    refuses(artifact({ "assets/index.js": `const a=/${behind}!x)y/` }), "assets/index.js");
  });

  it("refuses a missing og.jpg, or one that is not the cover", () => {
    refuses(artifact({ "og.jpg": null }), "og.jpg");
    refuses(artifact({ "og.jpg": "not the cover" }), "og.jpg");
  });

  it("refuses a demo over 5 MB", () => {
    refuses(artifact({ "assets/big.woff2": Buffer.alloc(5 * 1024 * 1024) }), "5 MB");
  });

  it("needs a folder", () => {
    expect(check().status).toBe(2);
    expect(check(join(tmpdir(), "check-demo-no-such-folder")).status).toBe(2);
  });
});
