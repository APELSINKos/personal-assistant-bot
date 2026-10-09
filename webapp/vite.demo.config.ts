import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// The live demo for GitHub Pages (spec §4.2): the host page and the unchanged app in its frame,
// built from demo/ into dist-demo. Paths below resolve against root; no node: imports, as tsc
// checks this file too.

/** The server's CSP without Telegram's script and without any network at all (spec §7.2). */
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'none'",
  "frame-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

/**
 * The CSP as the first tag of each page's head, in the build only: in dev:demo it would close the
 * connection of Vite's hot reload. A policy from <meta> covers only what comes after it, and Vite
 * puts its module script and preload links into the head.
 */
function contentSecurityPolicy(): Plugin {
  return {
    name: "demo-csp",
    apply: "build",
    transformIndexHtml: () => [
      { tag: "meta", attrs: { "http-equiv": "Content-Security-Policy", content: CSP }, injectTo: "head-prepend" },
    ],
  };
}

export default defineConfig({
  root: "demo",
  // Relative addresses: the site lives under /personal-assistant-bot/, and nothing names that path.
  base: "./",
  // No .env file and no VITE_* variable may reach a public build: no variable starts so.
  envDir: false,
  envPrefix: "DEMO_NONE_",
  plugins: [react(), contentSecurityPolicy()],
  // The pages load the app's sources as /src/…, as webapp/index.html does: the sources lie beside
  // root, not in it, and dev:demo would answer a path that leaves root with its page instead.
  resolve: { alias: { "/src": "../src" } },
  build: {
    outDir: "../dist-demo",
    // The folder is outside root: without this Vite would leave old files in it.
    emptyOutDir: true,
    target: "es2022",
    // Never inline an asset: font-src 'self' refuses fonts as data: URLs.
    assetsInlineLimit: 0,
    // The polyfill loads modules with fetch, which connect-src 'none' refuses.
    modulePreload: { polyfill: false },
    rolldownOptions: { input: { index: "index.html", app: "app.html" } },
  },
  // The app's sources, and the sample pictures of the share sheet in dev:demo.
  server: { fs: { allow: ["..", "../../docs/images"] } },
});
