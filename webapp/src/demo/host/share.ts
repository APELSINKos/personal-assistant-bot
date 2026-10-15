/**
 * What the demo's chat picker shows (spec §4.3): in place of Telegram's list of chats, the picture
 * the app would send — the README's sample of it, in the visitor's language and marked as an
 * example. The samples are files of the build, imported from docs/images.
 */
import forecastEn from "../../../../docs/images/forecast-card.en.jpg";
import forecastRu from "../../../../docs/images/forecast-card.jpg";
import habitEn from "../../../../docs/images/habit-card.en.jpg";
import habitRu from "../../../../docs/images/habit-card.jpg";
import type { Lang } from "../../i18n";
import { preparedPicture, type Picture } from "../api/prepared";
import { h } from "./dom";
import type { HostWords } from "./words";

const SAMPLES: Record<Picture, Record<Lang, string>> = {
  habit: { ru: habitRu, en: habitEn },
  forecast: { ru: forecastRu, en: forecastEn },
};

/** The sample of the picture a prepared message holds, with its mark. */
export function sample(preparedId: string, language: Lang, words: HostWords): HTMLElement {
  const picture = preparedPicture(preparedId);
  return h(
    "figure",
    { class: "share-sample" },
    h("img", { src: SAMPLES[picture][language], alt: words.sample[picture], width: "1080", height: "1350" }),
    // The picture's alt says it is an example already.
    h("span", { class: "share-sample__mark", "aria-hidden": "true" }, words.example),
  );
}
