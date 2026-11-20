import { createPortal } from "react-dom";
import type { View } from "./urlState";

const LINKS: readonly { readonly view: View; readonly href: string; readonly text: string }[] = [
  { view: "forecast", href: "#forecast", text: "Forecast" },
  { view: "accuracy", href: "#accuracy", text: "Accuracy" },
];

/**
 * The header's links, drawn into the empty `<nav id="site-nav">` that index.html holds, so they
 * are part of the app but sit in the page's header. Draws nothing when the page has no such element.
 */
export function SiteNav({ view }: { readonly view: View }) {
  const target = document.getElementById("site-nav");
  if (target === null) return null;
  return createPortal(
    <ul>
      {LINKS.map((link) => (
        <li key={link.view}>
          <a href={link.href} aria-current={link.view === view ? "page" : undefined}>
            {link.text}
          </a>
        </li>
      ))}
    </ul>,
    target,
  );
}
