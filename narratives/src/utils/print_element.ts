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
  if (!target) return;

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
  // then trigger the platform print dialog.
  requestAnimationFrame(() => {
    window.print();
    window.removeEventListener("beforeprint", onBeforePrint);
    delete document.body.dataset.printTarget;
    delete target.dataset.printActive;
    for (const a of ancestors) delete a.dataset.printAncestor;
  });
}
