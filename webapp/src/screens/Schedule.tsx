import { useRef, useState, type FormEvent } from "react";
import {
  errorCode,
  useConnectSchedule,
  useDisconnectSchedule,
  useGroups,
  useMe,
  useRefreshSchedule,
  useSchedule,
  useScheduleAlerts,
  useScheduleRefreshing,
  useUploadSchedule,
} from "../api/queries";
import type { AlertMinutes, ScheduleSource } from "../api/types";
import { Card } from "../components/Card";
import { SearchStatus } from "../components/SearchStatus";
import { ErrorState, Loader } from "../components/States";
import { toast } from "../components/toastStore";
import { WriteRefusedCard } from "../components/WriteRefusedCard";
import { errorText, useLang, useT } from "../i18n";
import { shortMoment } from "../lib/format";
import { useDebounced } from "../lib/useDebounced";
import { useWriteAccess } from "../lib/useWriteAccess";
import { confirmAction, haptic } from "../telegram";

const ALERT_CHOICES: (AlertMinutes | null)[] = [null, 5, 10, 15, 30, 60];
const FILE_LIMIT = 2 * 1024 * 1024;

/** Three ways in: a MIREA group by name, a calendar link, or an .ics file. */
function ConnectForm({ onDone, onCancel }: { onDone: () => void; onCancel?: () => void }) {
  const t = useT();
  const [query, setQuery] = useState("");
  const search = useDebounced(query, 300);
  const groups = useGroups(search);
  const [link, setLink] = useState("");
  const connect = useConnectSchedule();
  const upload = useUploadSchedule();
  const fileInput = useRef<HTMLInputElement>(null);
  const busy = connect.isPending || upload.isPending;
  // Awaited rather than passed as `mutate` callbacks: connecting the first source swaps this form
  // for the source card before the request settles, and callbacks of an unmounted form never run.
  const run = async (work: Promise<unknown>) => {
    try {
      await work;
    } catch {
      return; // the mutation cache's own handler already showed a toast
    }
    toast({ kind: "success", text: t.schedule.connected });
    onDone();
  };
  // Both the live query and the debounced one must be long enough, so the suggestions vanish at
  // once when the field is cleared instead of lingering for the debounce delay.
  const searching = query.trim().length >= 2 && search.trim().length >= 2;
  const found = searching && groups.data ? groups.data.groups.length : 0;

  const submitLink = (event: FormEvent) => {
    event.preventDefault();
    if (link.trim() && !busy) void run(connect.mutateAsync({ url: link.trim() }));
  };
  const pickFile = (file: File | undefined) => {
    if (!file) return;
    if (file.size > FILE_LIMIT) {
      // The same cue as a server error gets in the mutation cache's handler.
      haptic("error");
      toast({ kind: "error", code: "too_large" });
    } else void run(upload.mutateAsync(file));
  };

  return (
    <>
      {!onCancel && <p className="muted schedule__intro">{t.schedule.intro}</p>}

      <Card title={t.schedule.group} index={0}>
        <label className="field">
          <span className="visually-hidden">{t.schedule.group}</span>
          <input
            className="input"
            type="search"
            maxLength={40}
            placeholder={t.schedule.groupPlaceholder}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        {searching && groups.data && groups.data.groups.length > 0 && (
          <div className="results">
            {groups.data.groups.map((group) => (
              <button
                type="button"
                key={group.id}
                className="result"
                disabled={busy}
                onClick={() => void run(connect.mutateAsync({ mirea_id: group.id }))}
              >
                {group.name}
              </button>
            ))}
          </div>
        )}
        <SearchStatus count={found > 0 ? t.schedule.groupsFound(found) : null}>
          {searching && groups.isError && !groups.data && (
            <p className="muted">{errorText(t, errorCode(groups.error))}</p>
          )}
          {searching && groups.data?.building && <p className="muted">{t.schedule.building}</p>}
          {searching && groups.data && !groups.data.building && groups.data.groups.length === 0 && (
            <p className="muted">{t.schedule.noGroups}</p>
          )}
        </SearchStatus>
      </Card>

      <Card title={t.schedule.link} index={1}>
        <form onSubmit={submitLink}>
          <label className="field">
            <span className="visually-hidden">{t.schedule.link}</span>
            {/* Plain text, not type="url": the browser's own check would stop a link it doesn't
                like with its own message; the server explains what is wrong instead. */}
            <input
              className="input"
              type="text"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              maxLength={2000}
              placeholder={t.schedule.linkPlaceholder}
              value={link}
              onChange={(event) => setLink(event.target.value)}
            />
          </label>
          <button type="submit" className="button button--primary" disabled={busy || !link.trim()}>
            {t.schedule.connect}
          </button>
        </form>
      </Card>

      <Card title={t.schedule.file} index={2}>
        <p className="muted">{t.schedule.fileHint}</p>
        <input
          ref={fileInput}
          type="file"
          accept=".ics,text/calendar"
          hidden
          onChange={(event) => {
            pickFile(event.target.files?.[0]);
            event.target.value = ""; // picking the same file again still counts
          }}
        />
        <button type="button" className="button" disabled={busy} onClick={() => fileInput.current?.click()}>
          {t.schedule.pickFile}
        </button>
      </Card>

      {onCancel && (
        <button type="button" className="button schedule__cancel" onClick={onCancel}>
          {t.schedule.cancel}
        </button>
      )}
    </>
  );
}

function SourceCard({ source, zone, onChange }: { source: ScheduleSource; zone: string; onChange: () => void }) {
  const t = useT();
  const lang = useLang();
  const refresh = useRefreshSchedule();
  const refreshing = useScheduleRefreshing();
  const disconnect = useDisconnectSchedule();
  const when = shortMoment(source.ok_at ?? source.fetched_at, zone, lang);

  const turnOff = async () => {
    if (await confirmAction(t.schedule.confirmDisconnect)) disconnect.mutate();
  };

  return (
    <Card title={t.schedule.kinds[source.kind]} index={0}>
      <p className="schedule__title">{source.title ?? t.schedule.untitled}</p>
      {source.stale ? (
        <p>⚠️ {t.schedule.stale(when)}</p>
      ) : (
        <p className="muted">{t.schedule.updated(when)}</p>
      )}
      {source.error && !source.stale && <p className="muted">{t.schedule.failed}</p>}
      <p className="muted">{source.lessons_ahead ? t.schedule.ahead(source.lessons_ahead) : t.schedule.empty}</p>
      {source.kind === "file" && <p className="muted">{t.schedule.fileHint}</p>}
      <div className="schedule__actions">
        {source.kind !== "file" && (
          <button type="button" className="button" disabled={refreshing} onClick={() => refresh.mutate()}>
            {t.schedule.refresh}
          </button>
        )}
        <button type="button" className="button" onClick={onChange}>
          {t.schedule.change}
        </button>
        <button
          type="button"
          className="button button--danger"
          disabled={disconnect.isPending}
          onClick={() => void turnOff()}
        >
          {t.schedule.disconnect}
        </button>
      </div>
    </Card>
  );
}

function AlertsCard({ source, canWrite }: { source: ScheduleSource; canWrite: boolean }) {
  const t = useT();
  const alerts = useScheduleAlerts();
  const write = useWriteAccess(canWrite);
  // The pressed choice shows at once; the saved one takes over when the request settles.
  const shown = alerts.isPending ? alerts.variables : source.lesson_reminder_minutes;

  const choose = async (minutes: AlertMinutes | null) => {
    // An alert is a message from the bot: it needs the permission to write first.
    if (minutes !== null && !(await write.ensure())) return;
    alerts.mutate(minutes);
  };

  return (
    <>
      <Card title={t.schedule.alerts} index={1}>
        <div className="segmented" role="group" aria-label={t.schedule.alerts}>
          {ALERT_CHOICES.map((minutes) => (
            <button
              type="button"
              key={minutes ?? "off"}
              className="segmented__option"
              aria-pressed={shown === minutes}
              onClick={() => void choose(minutes)}
            >
              {minutes === null ? t.schedule.alertOff : t.schedule.alertMinutes(minutes)}
            </button>
          ))}
        </div>
      </Card>
      {write.refused && <WriteRefusedCard />}
    </>
  );
}

export function ScheduleScreen() {
  const t = useT();
  const me = useMe();
  const schedule = useSchedule();
  const [changing, setChanging] = useState(false);

  if (me.isError) return <ErrorState onRetry={() => void me.refetch()} />;
  if (schedule.isError) return <ErrorState onRetry={() => void schedule.refetch()} />;
  if (me.isPending || schedule.isPending) return <Loader />;

  const source = schedule.data.source;
  return (
    <>
      <h1 className="screen__title">{t.schedule.title}</h1>
      {source && !changing ? (
        <>
          <SourceCard source={source} zone={me.data.city.timezone} onChange={() => setChanging(true)} />
          <AlertsCard source={source} canWrite={me.data.can_write} />
        </>
      ) : (
        <ConnectForm onDone={() => setChanging(false)} onCancel={source ? () => setChanging(false) : undefined} />
      )}
    </>
  );
}
