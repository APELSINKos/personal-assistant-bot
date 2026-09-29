import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { matchRoute, Route, Router, Switch, useLocation, useRouter } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { AUTH_EXPIRED_EVENT } from "./api/client";
import { createQueryClient, useMe } from "./api/queries";
import { BottomNav } from "./components/BottomNav";
import { Toasts } from "./components/Toasts";
import { LangProvider, resolveLang, useT } from "./i18n";
import { ROUTES } from "./routes";
import {
  colorScheme, initData, isDevSession, onThemeChange, paintTelegram, telegramLanguage, useBackButton,
  webApp,
} from "./telegram";

function fallbackLang() {
  return resolveLang(telegramLanguage() ?? navigator.language);
}

function Reopen({ outside }: { outside: boolean }) {
  const t = useT();
  return (
    <div className="reopen">
      <div>
        <p className="reopen__title">{t.auth.title}</p>
        <p className="muted">{outside ? t.auth.outside : t.auth.expired}</p>
      </div>
    </div>
  );
}

function SessionGate({ children }: { children: ReactNode }) {
  const [expired, setExpired] = useState(() => initData() === null);
  useEffect(() => {
    const onExpired = () => setExpired(true);
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);
  if (!expired) return children;
  return (
    <LangProvider lang={fallbackLang()}>
      <Reopen outside={webApp() === null && !isDevSession()} />
    </LangProvider>
  );
}

function useTheme() {
  const [scheme, setScheme] = useState(colorScheme);
  useEffect(() => onThemeChange(() => setScheme(colorScheme())), []);
  useEffect(() => {
    document.documentElement.dataset.theme = scheme;
    paintTelegram(scheme);
  }, [scheme]);
}

function Localized({ children }: { children: ReactNode }) {
  const me = useMe();
  const lang = me.data?.language ?? fallbackLang();
  useTheme();
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  return <LangProvider lang={lang}>{children}</LangProvider>;
}

function Shell() {
  const t = useT();
  const [location, navigate] = useLocation();
  const { parser } = useRouter();
  const current = ROUTES.find((route) => matchRoute(parser, route.path, location)[0]);
  const parent = current?.parent;
  useBackButton(parent ? () => navigate(parent) : null);
  return (
    <div className={current?.hideNav ? "app app--no-nav" : "app"}>
      {isDevSession() && <div className="dev-badge">{t.common.dev}</div>}
      <main className="screen">
        <Switch>
          {ROUTES.map((route) => (
            <Route key={route.path} path={route.path} component={route.component} />
          ))}
        </Switch>
      </main>
      {!current?.hideNav && <BottomNav />}
      <Toasts />
    </div>
  );
}

export function App() {
  const [client] = useState(createQueryClient);
  return (
    <QueryClientProvider client={client}>
      <Router hook={useHashLocation}>
        <SessionGate>
          <Localized>
            <Shell />
          </Localized>
        </SessionGate>
      </Router>
    </QueryClientProvider>
  );
}
