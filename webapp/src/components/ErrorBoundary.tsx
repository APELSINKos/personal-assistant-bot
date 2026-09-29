import { Component, type ReactNode } from "react";
import { LangProvider, resolveLang } from "../i18n";
import { telegramLanguage } from "../telegram";
import { ErrorState } from "./States";

interface Props {
  children: ReactNode;
  reload?: () => void;
}

/** The last line of defence: an error while rendering shows the error state, not a blank page. */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    const reload = this.props.reload ?? (() => window.location.reload());
    // It sits above the app's LangProvider, so the language comes from Telegram or the browser.
    return (
      <LangProvider lang={resolveLang(telegramLanguage() ?? navigator.language)}>
        <ErrorState onRetry={reload} />
      </LangProvider>
    );
  }
}
