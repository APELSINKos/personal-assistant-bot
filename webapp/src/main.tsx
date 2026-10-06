// Whole weights: each subset is declared with its unicode-range, so a page downloads only the
// subsets its text needs (a subset file alone has no range and would claim every character).
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "@fontsource/unbounded/700.css";
import "./styles/tokens.css";
import "./styles/app.css";
import "./styles/money.css";
import "./styles/weather.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { normalizeLaunchHash, startTelegram } from "./telegram";

normalizeLaunchHash();
startTelegram();

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
