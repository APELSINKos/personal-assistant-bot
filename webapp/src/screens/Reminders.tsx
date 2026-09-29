import { useDeleteReminder, useReminders } from "../api/queries";
import { Fab } from "../components/Fab";
import { Empty, ErrorState, Loader } from "../components/States";
import { SwipeRow } from "../components/SwipeRow";
import { useLang, useT } from "../i18n";
import { groupByDay, localTodayIso, timeOf } from "../lib/format";
import { useCityZone } from "../lib/zone";
import { confirmAction } from "../telegram";

export function RemindersScreen() {
  const t = useT();
  const lang = useLang();
  const zone = useCityZone();
  const reminders = useReminders();
  const remove = useDeleteReminder();

  if (reminders.isPending) return <Loader />;
  if (reminders.isError) return <ErrorState onRetry={() => void reminders.refetch()} />;

  const groups = groupByDay(reminders.data, localTodayIso(zone), lang, {
    today: t.reminders.today,
    tomorrow: t.reminders.tomorrow,
  });
  const onDelete = async (id: number) => {
    if (await confirmAction(t.reminders.confirmDelete)) remove.mutate(id);
  };

  return (
    <>
      <h1 className="screen__title">{t.tabs.reminders}</h1>
      {groups.length === 0 ? (
        <Empty text={t.reminders.empty} />
      ) : (
        groups.map((group) => (
          <section key={group.day}>
            <h2 className="group__label">{group.label}</h2>
            {group.items.map((item) => (
              <SwipeRow key={item.id} onDelete={() => void onDelete(item.id)} deleteLabel={t.reminders.delete}>
                <span className="time">{timeOf(item.due_local)}</span>
                {item.text}
              </SwipeRow>
            ))}
          </section>
        ))
      )}
      <Fab href="/reminders/new" label={t.reminders.add} />
    </>
  );
}
