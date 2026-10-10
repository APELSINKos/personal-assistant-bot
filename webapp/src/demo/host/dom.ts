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
 * The icons of Telegram's chrome and of the status bar, drawn rather than typed: Manrope has no ✕
 * or ⋯, and the font a browser takes them from instead differs from one machine to another (spec
 * §6.4). Each is its view box and its shapes.
 */
const ICONS = {
  close: [
    "0 0 24 24",
    '<path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  ],
  back: [
    "0 0 24 24",
    '<path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
      + 'stroke-linejoin="round"/>',
  ],
  more: [
    "0 0 24 24",
    '<circle cx="5" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="2" fill="currentColor"/>'
      + '<circle cx="19" cy="12" r="2" fill="currentColor"/>',
  ],
  signal: [
    "0 0 18 12",
    '<rect x="0" y="8" width="3" height="4" rx="1" fill="currentColor"/>'
      + '<rect x="5" y="5.5" width="3" height="6.5" rx="1" fill="currentColor"/>'
      + '<rect x="10" y="3" width="3" height="9" rx="1" fill="currentColor"/>'
      + '<rect x="15" y="0" width="3" height="12" rx="1" fill="currentColor"/>',
  ],
  wifi: [
    "0 0 16 12",
    '<path d="M8 10.6l2-2.2a2.9 2.9 0 0 0-4 0z" fill="currentColor"/>'
      + '<path d="M2.6 5.1a7.7 7.7 0 0 1 10.8 0M4.9 7.6a4.5 4.5 0 0 1 6.2 0" fill="none" stroke="currentColor" '
      + 'stroke-width="1.7" stroke-linecap="round"/>',
  ],
  battery: [
    "0 0 27 13",
    '<rect x="0.75" y="0.75" width="22.5" height="11.5" rx="3.5" fill="none" stroke="currentColor" '
      + 'stroke-width="1.5" opacity="0.45"/><rect x="2.5" y="2.5" width="16" height="8" rx="2" fill="currentColor"/>'
      + '<path d="M25 4.5v4a2 2 0 0 0 0-4z" fill="currentColor" opacity="0.45"/>',
  ],
} as const;

export type IconName = keyof typeof ICONS;

/** An icon, hidden from screen readers: the button around it carries the name. */
export function icon(name: IconName): SVGSVGElement {
  const [viewBox, shapes] = ICONS[name];
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", viewBox);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("class", `icon icon--${name}`);
  svg.innerHTML = shapes;
  return svg;
}
