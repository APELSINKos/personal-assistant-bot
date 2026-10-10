import { describe, expect, it } from "vitest";
import type { GroupSearch, ScheduleState } from "../../api/types";
import { demoApi, MORNING, problem } from "./testApi";
import { HOUR } from "./time";

const NO_CONTENT = { status: 204, body: null, headers: {} };

/** A calendar file as the app sends it: through the bridge it comes as its name, type and size. */
function upload(demo: ReturnType<typeof demoApi>, name: string | null, size = 15_000) {
  const search = name === null ? "" : `?name=${encodeURIComponent(name)}`;
  return demo.api({ method: "POST", path: "/schedule/file", search, body: { file: name ?? "", type: "text/calendar", size } });
}

describe("the timetable (routers/schedule.py, services/schedule.py)", () => {
  it("GET /schedule: the demo's group, connected, with the lessons ahead", () => {
    const { source } = demoApi().read<ScheduleState>("GET /schedule");
    expect(source).toEqual({
      kind: "mirea", title: "ДЕМО-01-26", mirea_id: 4242, url: null,
      fetched_at: "2026-10-07T05:30:00Z", ok_at: "2026-10-07T05:30:00Z", error: null, stale: false,
      lesson_reminder_minutes: 10, lessons_ahead: expect.any(Number),
    });
    expect(source?.lessons_ahead).toBeGreaterThan(20);
    expect(demoApi("en").read<ScheduleState>("GET /schedule").source?.title).toBe("DEMO-01-26");
  });

  it("GET /schedule/groups: any search of two characters or more finds the demo's group", () => {
    const { read, call } = demoApi();
    const found = { groups: [{ id: 4242, name: "ДЕМО-01-26" }], building: false };
    expect(read<GroupSearch>(`GET /schedule/groups?q=${encodeURIComponent("ИКБО-63-24")}`)).toEqual(found);
    expect(read<GroupSearch>("GET /schedule/groups?q=xy")).toEqual(found);
    expect(read<GroupSearch>(`GET /schedule/groups?q=${encodeURIComponent("И")}`)).toEqual({ groups: [], building: false });
    expect(read<GroupSearch>("GET /schedule/groups")).toEqual({ groups: [], building: false });
    expect(call(`GET /schedule/groups?q=${"x".repeat(41)}`)).toEqual(problem(422, "validation_error", { field: "q", limit: 40 }));
  });

  it("PUT /schedule: the group, or a link, which keeps the sample lessons", () => {
    const { read, call, setNow } = demoApi();
    setNow(MORNING + HOUR);
    expect(read<ScheduleState>("PUT /schedule", { url: " webcal://example.com/my.ics " }).source).toMatchObject({
      kind: "url", title: "example.com", mirea_id: null, url: "https://example.com/my.ics",
      fetched_at: "2026-10-07T08:30:00Z", lesson_reminder_minutes: 10,
    });
    expect(read<ScheduleState>("PUT /schedule", { mirea_id: 4242 }).source).toMatchObject({
      kind: "mirea", title: "ДЕМО-01-26", mirea_id: 4242, url: null,
    });
    expect(call("PUT /schedule", { mirea_id: 4805 })).toEqual(problem(404, "not_found", { entity: "group" }));
    for (const url of ["http://example.com/a.ics", "https://user:pw@example.com/a.ics", "https://example.com:8443/a.ics", "calendar"]) {
      expect(call("PUT /schedule", { url }), url).toEqual(problem(422, "validation_error", { field: "url", reason: "forbidden_host" }));
    }
    expect(call("PUT /schedule", {})).toEqual(problem(422, "validation_error", { field: "schedule", reason: "source" }));
    expect(call("PUT /schedule", { mirea_id: 4242, url: "https://example.com/a.ics" })).toEqual(
      problem(422, "validation_error", { field: "schedule", reason: "source" }),
    );
  });

  it("POST /schedule/file: a calendar file up to 2 MB, named by its file", () => {
    const demo = demoApi();
    expect(upload(demo, "МИРЭА.ics")).toMatchObject({ status: 200, body: { source: { kind: "file", title: "МИРЭА", url: null, mirea_id: null } } });
    expect(upload(demo, null)).toMatchObject({ status: 200, body: { source: { kind: "file", title: null } } });
    expect(upload(demo, "big.ics", 2 * 1024 * 1024 + 1)).toEqual(
      problem(422, "validation_error", { field: "file", reason: "too_large" }),
    );
    expect(upload(demo, `${"x".repeat(252)}.ics`)).toEqual(problem(422, "validation_error", { field: "name", limit: 255 }));
  });

  it("POST /schedule/file: a long name cut at 100 characters, an emoji whole", () => {
    const demo = demoApi();
    // schedule._store cuts the title in code points: never half of an emoji's surrogate pair.
    expect(upload(demo, `a${"📅".repeat(100)}.ics`)).toMatchObject({
      status: 200, body: { source: { title: `a${"📅".repeat(99)}` } },
    });
  });

  it("POST /schedule/refresh: fetched again now; 404 without a timetable", () => {
    const { read, call, setNow } = demoApi();
    setNow(MORNING + HOUR);
    expect(read<ScheduleState>("POST /schedule/refresh").source).toMatchObject({
      fetched_at: "2026-10-07T08:30:00Z", ok_at: "2026-10-07T08:30:00Z", error: null,
    });
    call("DELETE /schedule");
    expect(call("POST /schedule/refresh")).toEqual(problem(404, "not_found", { entity: "schedule" }));
  });

  it("PATCH /schedule: the reminder before a lesson, or none", () => {
    const { read, call } = demoApi();
    expect(read<ScheduleState>("PATCH /schedule", { lesson_reminder_minutes: 30 }).source?.lesson_reminder_minutes).toBe(30);
    expect(read<ScheduleState>("PATCH /schedule", { lesson_reminder_minutes: null }).source?.lesson_reminder_minutes).toBeNull();
    expect(call("PATCH /schedule", { lesson_reminder_minutes: 7 })).toEqual(
      problem(422, "validation_error", { field: "lesson_reminder_minutes" }),
    );
    expect(call("PATCH /schedule", {})).toEqual(
      problem(422, "validation_error", { field: "lesson_reminder_minutes", detail: "Field required" }),
    );
    call("DELETE /schedule");
    expect(call("PATCH /schedule", { lesson_reminder_minutes: 10 })).toEqual(problem(404, "not_found", { entity: "schedule" }));
  });

  it("DELETE /schedule: disconnected, then 404", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /schedule")).toEqual(NO_CONTENT);
    expect(read<ScheduleState>("GET /schedule")).toEqual({ source: null });
    expect(call("DELETE /schedule")).toEqual(problem(404, "not_found", { entity: "schedule" }));
    expect(read<ScheduleState>("PUT /schedule", { mirea_id: 4242 }).source?.lesson_reminder_minutes).toBeNull();
  });
});
