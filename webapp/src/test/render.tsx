import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { createQueryClient } from "../api/queries";
import { LangProvider, type Lang } from "../i18n";

export function renderWithApp(
  ui: ReactElement,
  { path = "/", lang = "ru" }: { path?: string; lang?: Lang } = {},
) {
  const client = createQueryClient();
  // The app's own retries, without the 1 s and 2 s it waits before them.
  const defaults = client.getDefaultOptions();
  client.setDefaultOptions({ ...defaults, queries: { ...defaults.queries, retryDelay: 0 } });
  const location = memoryLocation({ path, record: true });
  const result = render(
    <QueryClientProvider client={client}>
      <Router hook={location.hook}>
        <LangProvider lang={lang}>{ui}</LangProvider>
      </Router>
    </QueryClientProvider>,
  );
  return { ...result, client, navigate: location.navigate, history: location.history };
}
