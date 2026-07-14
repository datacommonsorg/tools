/**
 * @fileoverview Prints a DOM element to PDF via a scoped print window.
 */

/**
 * Print a single DOM element via the browser's native print pipeline.
 *
 * The element is tagged with `data-print-active`; the @media print rules in
 * index.css hide everything else on the page (visibility: hidden across the
 * document, visibility: visible on the active subtree only). After the print
 * dialog closes the tags are removed so the page returns to normal.
 *
 * This replaces the older "hardcoded #answer-panel" strategy that printed
 * EVERY answer panel in the chat — there are now many answer panels in a
 * conversation, each must be exportable in isolation.
 */
export function printElement(target: HTMLElement | null) {
  // Bail if the element is missing, has been detached by a concurrent React
  // re-render, or a print sequence is already in flight. The last guard makes
  // this atomic: a double-click, or clicking Export on two panels in quick
  // succession, would otherwise tag BOTH subtrees before the first
  // requestAnimationFrame fires and print them together.
  if (
    !target ||
    !target.isConnected ||
    document.body.dataset.printTarget === "true"
  ) {
    return;
  }

  // Walk up the DOM marking each ancestor with `data-print-ancestor`. The
  // print stylesheet hides every element that is neither an ancestor nor
  // inside the active subtree — this collapses layout (display:none) on
  // siblings instead of just hiding them with visibility, so the printed
  // PDF contains only the selected Q&A panel and no blank pages from
  // surrounding chrome / other turns.
  const ancestors: HTMLElement[] = [];
  let node: HTMLElement | null = target.parentElement;
  while (node && node !== document.body) {
    ancestors.push(node);
    node.dataset.printAncestor = "true";
    node = node.parentElement;
  }
  document.body.dataset.printTarget = "true";
  target.dataset.printActive = "true";

  // When the browser switches to print layout the DC web components'
  // internal ResizeObserver needs to fire so their SVGs redraw at the
  // narrower print-page width instead of staying at the on-screen
  // measurement. `beforeprint` runs AFTER the print layout is committed
  // but BEFORE the page is snapshot; dispatching a resize here lets the
  // observer pick up the new width synchronously.
  const onBeforePrint = () => {
    window.dispatchEvent(new Event("resize"));
  };
  window.addEventListener("beforeprint", onBeforePrint);

  // Defer so any state-driven class updates (e.g. focus rings) flush first,
  // then trigger the platform print dialog. The cleanup runs in `finally` so
  // the print-state tags are always removed even if window.print() throws —
  // otherwise the printTarget guard above would wedge and block every
  // subsequent print.
  requestAnimationFrame(() => {
    try {
      window.print();
    } finally {
      window.removeEventListener("beforeprint", onBeforePrint);
      delete document.body.dataset.printTarget;
      delete target.dataset.printActive;
      for (const ancestor of ancestors) delete ancestor.dataset.printAncestor;
      // Now that the print-only @media rules no longer apply, tell the DC
      // components to redraw their SVGs back to the on-screen width they had
      // before the resize we dispatched in `beforeprint`.
      window.dispatchEvent(new Event("resize"));
    }
  });
}
