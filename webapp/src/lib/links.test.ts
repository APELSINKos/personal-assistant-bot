import { describe, expect, it } from "vitest";
import { dict } from "../i18n";
import { installTelegram } from "../test/fakeTelegram";
import {
  creditParts, findLinks, GEONAMES_URL, LICENCE_URL, linkParts, OPEN_METEO_URL, openAddress,
} from "./links";

/** The addresses a text gives: what each tap would open. */
const urls = (text: string) => linkParts(text).flatMap((part) => (part.url === null ? [] : [part.url]));

describe("addresses in a note", () => {
  it("cuts a text into plain parts and addresses, losing nothing", () => {
    const text = "Скидки тут (https://example.com/sale), а чат — t.me/x.";
    const parts = linkParts(text);
    expect(parts).toEqual([
      { text: "Скидки тут (", url: null },
      { text: "https://example.com/sale", url: "https://example.com/sale" },
      { text: "), а чат — ", url: null },
      { text: "t.me/x", url: "https://t.me/x" },
      { text: ".", url: null },
    ]);
    expect(parts.map((part) => part.text).join("")).toBe(text);
  });

  it("takes http, https and t.me only", () => {
    expect(urls("http://x.ru https://y.ru T.ME/z ftp://f.ru example.com mailto:a@b.ru")).toEqual([
      "http://x.ru", "https://y.ru", "https://T.ME/z",
    ]);
    expect(urls("gist.me/abc")).toEqual([]); // «t.me/» inside another word is no address
    expect(urls("https:// и всё")).toEqual([]);
    expect(linkParts("")).toEqual([]);
    expect(linkParts("без адресов")).toEqual([{ text: "без адресов", url: null }]);
  });

  it("leaves out the punctuation that ends the sentence", () => {
    expect(urls("см. https://x.ru/a.")).toEqual(["https://x.ru/a"]);
    expect(urls("https://x.ru/a, https://x.ru/b; https://x.ru/c: https://x.ru/d!")).toEqual([
      "https://x.ru/a", "https://x.ru/b", "https://x.ru/c", "https://x.ru/d",
    ]);
    expect(urls("Правда https://x.ru/a?! И https://x.ru/b…")).toEqual(["https://x.ru/a", "https://x.ru/b"]);
    expect(urls("'https://x.ru/a' и ‘https://x.ru/b’")).toEqual(["https://x.ru/a", "https://x.ru/b"]);
  });

  it("drops a closing bracket only when the address has no pair for it", () => {
    expect(urls("текст (https://x.ru/a).")).toEqual(["https://x.ru/a"]);
    expect(urls("https://ru.wikipedia.org/wiki/Мир_(значения)")).toEqual([
      "https://ru.wikipedia.org/wiki/Мир_(значения)",
    ]);
    expect(urls("(см. https://ru.wikipedia.org/wiki/Мир_(значения))")).toEqual([
      "https://ru.wikipedia.org/wiki/Мир_(значения)",
    ]);
  });

  it("keeps the quotes and guillemets around an address out of it", () => {
    expect(urls("“https://x.ru” и \"https://y.ru\" и «https://z.ru» и „https://w.ru“")).toEqual([
      "https://x.ru", "https://y.ru", "https://z.ru", "https://w.ru",
    ]);
    expect(urls("<https://x.ru>")).toEqual(["https://x.ru"]);
  });

  it("lists each address of a text once, in order", () => {
    expect(findLinks("https://b.ru, t.me/a и снова https://b.ru")).toEqual([
      { text: "https://b.ru", url: "https://b.ru" },
      { text: "t.me/a", url: "https://t.me/a" },
    ]);
    expect(findLinks("ничего")).toEqual([]);
  });
});

describe("opening an address", () => {
  it("opens t.me and telegram.me inside Telegram, any other in the browser", () => {
    const app = installTelegram();
    openAddress("https://t.me/x");
    openAddress("http://telegram.me/y");
    openAddress("https://T.ME/z");
    expect(app.openTelegramLink).toHaveBeenNthCalledWith(1, "https://t.me/x");
    expect(app.openTelegramLink).toHaveBeenNthCalledWith(2, "http://telegram.me/y");
    expect(app.openTelegramLink).toHaveBeenNthCalledWith(3, "https://T.ME/z");
    openAddress("https://x.ru/a");
    openAddress("https://username.t.me/"); // openTelegramLink refuses any other host
    expect(app.openLink).toHaveBeenNthCalledWith(1, "https://x.ru/a");
    expect(app.openLink).toHaveBeenNthCalledWith(2, "https://username.t.me/");
    expect(app.openTelegramLink).toHaveBeenCalledTimes(3);
  });

  it("opens what a tap on an address in a note gives", () => {
    const app = installTelegram();
    for (const part of linkParts("чат t.me/x")) if (part.url !== null) openAddress(part.url);
    expect(app.openTelegramLink).toHaveBeenCalledWith("https://t.me/x");
  });
});

describe("credit lines", () => {
  it.each(["ru", "en"] as const)("makes links of all three sources in more.credits (%s)", (lang) => {
    const text = dict(lang).more.credits;
    const parts = creditParts(text);
    expect(parts.flatMap((part) => (part.url === null ? [] : [part.url]))).toEqual([
      OPEN_METEO_URL, GEONAMES_URL, LICENCE_URL,
    ]);
    expect(parts.map((part) => part.text).join("")).toBe(text);
  });
});
