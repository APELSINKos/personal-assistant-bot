// The demo's link preview (spec §4.2): after Vite, a copy of the project's cover goes into the build
// as og.jpg. Both paths start from this file, not from the working folder: the build runs from
// webapp/ and from the picture generator alike. No cover, no demo: the copy fails the build.
import { copyFileSync } from "node:fs";

copyFileSync(new URL("../../docs/images/cover.jpg", import.meta.url), new URL("../dist-demo/og.jpg", import.meta.url));
