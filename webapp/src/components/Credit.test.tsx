import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { dict } from "../i18n";
import { GEONAMES_URL, OPEN_METEO_URL } from "../lib/links";
import { installTelegram } from "../test/fakeTelegram";
import { Credit } from "./Credit";

/** The piece of the line a link is drawn in: the link and the punctuation that stays with it. */
const piece = (name: string) => screen.getByRole("button", { name }).parentElement;

describe("Credit", () => {
  it.each(["ru", "en"] as const)("keeps each link with the punctuation it touches, and loses nothing (%s)", (lang) => {
    const text = dict(lang).more.credits;
    const { container } = render(<Credit text={text} />);
    expect(container.textContent).toBe(text);
    expect(piece("open-meteo.com")).toHaveTextContent(/^open-meteo\.com,$/);
    expect(piece("geonames.org")).toHaveTextContent(/^geonames\.org;$/);
    // Not «… CC BY 4.0 (» at the end of one line and the address on the next.
    expect(piece("creativecommons.org/licenses/by/4.0")).toHaveTextContent(
      /^\(creativecommons\.org\/licenses\/by\/4\.0\),$/,
    );
  });

  it("keeps nothing more with a link that ends the line", () => {
    const { container } = render(<Credit text={dict("ru").weather.credit} />);
    expect(container.textContent).toBe("Данные о погоде: open-meteo.com");
    expect(piece("open-meteo.com")).toHaveTextContent(/^open-meteo\.com$/);
  });

  it("gives a mark between two links to the first of them, once", () => {
    const { container } = render(<Credit text="(open-meteo.com/geonames.org)" />);
    expect(container.textContent).toBe("(open-meteo.com/geonames.org)");
    expect(piece("open-meteo.com")).toHaveTextContent(/^\(open-meteo\.com\/$/);
    expect(piece("geonames.org")).toHaveTextContent(/^geonames\.org\)$/);
  });

  it("opens the source a link names", () => {
    const app = installTelegram();
    render(<Credit text={dict("en").more.credits} />);
    fireEvent.click(screen.getByRole("button", { name: "geonames.org" }));
    fireEvent.click(screen.getByRole("button", { name: "open-meteo.com" }));
    expect(app.openLink).toHaveBeenNthCalledWith(1, GEONAMES_URL);
    expect(app.openLink).toHaveBeenNthCalledWith(2, OPEN_METEO_URL);
  });
});
