/** The host page's elements, built by hand: the page has no framework of its own. */

type Attributes = Record<string, string | boolean | undefined>;

/** An element with its attributes (true gives an empty one, false and undefined none) and children. */
export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attributes: Attributes = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === true) element.setAttribute(name, "");
    else if (typeof value === "string") element.setAttribute(name, value);
  }
  element.append(...children);
  return element;
}

const SVG = "http://www.w3.org/2000/svg";

/**
 * The icons of Telegram's chrome, drawn rather than typed: Manrope has no ✕ or ⋯, and the font a
 * browser takes them from instead differs from one machine to another (spec §6.4).
 */
const ICONS = {
  close: '<path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  back: '<path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
  more: '<circle cx="5" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="19" cy="12" r="2" fill="currentColor"/>',
} as const;

export type IconName = keyof typeof ICONS;

/** An icon 24 units square, hidden from screen readers: the button around it carries the name. */
export function icon(name: IconName): SVGSVGElement {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("class", `icon icon--${name}`);
  svg.innerHTML = ICONS[name];
  return svg;
}
