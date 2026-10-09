/**
 * The demo's prepared messages (spec §4.3, §5.1). POST /habits/{id}/share and POST /weather/share
 * answer with an id that names the picture, and the host page's chat picker shows the sample of that
 * picture from the README; nothing is drawn or sent.
 */

/** The pictures the app can share: a habit's card or the week's forecast. */
export type Picture = "habit" | "forecast";

/** A prepared message's id: «demo-habit-7-1», «demo-forecast-0-2». */
export function preparedId(picture: Picture, ...parts: number[]): string {
  return ["demo", picture, ...parts].join("-");
}

/** The picture a prepared message's id names; the habit card, the first of them, for any other id. */
export function preparedPicture(id: string): Picture {
  return id.startsWith("demo-forecast-") ? "forecast" : "habit";
}
