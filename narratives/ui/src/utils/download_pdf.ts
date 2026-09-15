/**
 * @fileoverview Downloads an answer panel as a PDF file, without a print dialog.
 */


/** The Data Commons chart web components. */
const CHART_HOSTS = [
  "datacommons-line",
  "datacommons-bar",
  "datacommons-ranking",
  "datacommons-map",
  "datacommons-highlight",
  "datacommons-gauge",
  "datacommons-pie",
  "datacommons-scatter",
].join(",");

/** A4 at 96dpi, less ~12mm margins — the width the export is laid out at. */
const PAGE_WIDTH_PX = 717;
/** A4 aspect, used to slice the rendered canvas into pages. */
const A4_WIDTH_MM = 210;
const A4_HEIGHT_MM = 297;
const MARGIN_MM = 12;
/** The box a page image is placed into, once the margins are taken off. */
const A4_CONTENT_WIDTH_MM = A4_WIDTH_MM - MARGIN_MM * 2;
const A4_CONTENT_HEIGHT_MM = A4_HEIGHT_MM - MARGIN_MM * 2;

/** Rasterisation factor. 2 keeps chart labels legible without huge files. */
const CANVAS_SCALE = 2;
/** JPEG quality for the page images. */
const JPEG_QUALITY = 0.92;
/** Ceiling on chart upscaling, so a small chart is not blown up absurdly. */
const MAX_CHART_SCALE = 2;
/**
 * Least fraction of a page that must be filled before a break is moved up to
 * avoid splitting a chart. Below this, shifting the break would emit a page
 * that is mostly blank, which reads worse than the split it avoids.
 */
const MIN_PAGE_FILL = 0.25;
/**
 * The tallest a chart card may be, as a fraction of the page.
 *
 * The complement of MIN_PAGE_FILL, and that is the whole point of it: a card no
 * taller than this cannot reach either of pageBreak's escape hatches. It is
 * never taller than a page, and if it does cross a boundary it must begin more
 * than MIN_PAGE_FILL of the way down the page — so the break always moves and
 * the card always starts the next page whole. Charts that come out taller than
 * this are scaled down until they are not.
 */
export const MAX_CARD_PAGE_FILL = 1 - MIN_PAGE_FILL;
/**
 * Slack, in CSS px, taken off the height cap.
 *
 * pageBreak works in whole canvas pixels and floors the page height, so the cap
 * and the threshold it is the complement of can disagree by a fraction of a
 * pixel. A card sized to exactly the cap could fall a hair the wrong side of
 * MIN_PAGE_FILL and be split by that rounding alone.
 */
const CARD_HEIGHT_SLACK_PX = 4;

/** How long to wait for charts before exporting whatever has drawn. */
const CHART_TIMEOUT_MS = 20000;
const CHART_POLL_MS = 250;

/**
 * Computed properties copied onto cloned nodes.
 *
 * The chart lives in a shadow root styled with emotion (CSS-in-JS), so its
 * rules do not exist anywhere the clone can reach. Copying the *computed*
 * value of each property makes every cloned node self-describing, which is
 * what lets the chart survive being lifted into the light DOM.
 */
const STYLE_PROPS = [
  "display", "position", "top", "left", "right", "bottom", "float", "clear",
  "width", "height", "min-width", "min-height", "max-width", "max-height",
  "margin-top", "margin-right", "margin-bottom", "margin-left",
  "padding-top", "padding-right", "padding-bottom", "padding-left",
  "box-sizing", "overflow", "flex-direction", "flex-wrap", "justify-content",
  "align-items", "align-self", "flex-grow", "flex-shrink", "flex-basis", "gap",
  "grid-template-columns", "grid-template-rows",
  "color", "background-color", "opacity", "visibility",
  "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
  "border-top-color", "border-right-color", "border-bottom-color", "border-left-color",
  "border-top-style", "border-right-style", "border-bottom-style", "border-left-style",
  "border-radius",
  "font-family", "font-size", "font-weight", "font-style", "line-height",
  "letter-spacing", "text-align", "text-decoration", "text-transform",
  "white-space", "vertical-align",
  // SVG paint and geometry.
  "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
  "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
  "text-anchor", "dominant-baseline", "shape-rendering", "transform", "transform-origin",
];

/** True when a chart host has finished drawing a real chart. */
function chartIsDrawn(host: Element): boolean {
  const root = (host as Element & { shadowRoot: ShadowRoot | null }).shadowRoot;
  if (!root) return false;
  // A loading spinner also renders a small <svg>, so size is the discriminator:
  // the icon is ~16-22px, an actual chart is hundreds of px wide.
  const drawn = Array.from(root.querySelectorAll("svg")).some(
    (svg) => svg.getBoundingClientRect().width > 150,
  );
  return drawn && !/Loading/i.test(root.textContent ?? "");
}

/**
 * Waits for every chart to draw, resolving early once they all have.
 *
 * Resolves on timeout regardless: charts load unevenly and one occasionally
 * never finishes, and a stuck chart must not mean no PDF at all.
 */
function whenChartsDrawn(root: HTMLElement): Promise<void> {
  const hosts = Array.from(root.querySelectorAll(CHART_HOSTS));
  if (hosts.length === 0) return Promise.resolve();
  if (hosts.every(chartIsDrawn)) return Promise.resolve();

  return new Promise((resolve) => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      if (hosts.every(chartIsDrawn) || Date.now() - started > CHART_TIMEOUT_MS) {
        window.clearInterval(timer);
        resolve();
      }
    }, CHART_POLL_MS);
  });
}

/**
 * Deep-clones an element, writing each node's computed style inline.
 *
 * Walking both trees in parallel relies on cloneNode(true) preserving element
 * order exactly, which it does — querySelectorAll returns document order on
 * both sides.
 */
function cloneWithComputedStyles(source: Element): Element {
  const copy = source.cloneNode(true) as Element;
  const sourceNodes = [source, ...Array.from(source.querySelectorAll("*"))];
  const copyNodes = [copy, ...Array.from(copy.querySelectorAll("*"))];

  for (let i = 0; i < sourceNodes.length && i < copyNodes.length; i++) {
    const computed = window.getComputedStyle(sourceNodes[i]);
    const declarations: string[] = [];
    for (const prop of STYLE_PROPS) {
      const value = computed.getPropertyValue(prop);
      // Every non-empty value is copied, including "none". Dropping it is not
      // a harmless size saving: a line chart's path carries `fill: none`, and
      // without it SVG's default fill applies and every line renders as a
      // black blob.
      if (value) declarations.push(`${prop}:${value}`);
    }
    copyNodes[i].setAttribute("style", declarations.join(";"));
  }
  return copy;
}

/**
 * Replaces each chart web component in `clone` with a plain-DOM copy of what
 * that component drew.
 *
 * html2canvas cannot see into a shadow root, so without this every chart would
 * rasterise as an empty box. `original` supplies the live shadow content;
 * `clone` is the detached copy being prepared for rendering.
 */
function inlineCharts(clone: HTMLElement, original: HTMLElement) {
  const originalHosts = Array.from(original.querySelectorAll(CHART_HOSTS));
  const cloneHosts = Array.from(clone.querySelectorAll(CHART_HOSTS));

  originalHosts.forEach((host, index) => {
    const target = cloneHosts[index];
    if (!target) return;
    const root = (host as Element & { shadowRoot: ShadowRoot | null }).shadowRoot;
    const content = root?.firstElementChild;

    // Two boxes: an outer one that flows in the document and reserves the
    // scaled height, and an inner one held at the chart's natural width so it
    // can be scaled up to fill the page. The chart is drawn at whatever width
    // it happens to occupy on screen -- roughly half the card in the
    // two-column grid -- and scaling the SVG is lossless, so this fills the
    // page without asking the component to re-render.
    const box = document.createElement("div");
    box.style.width = "100%";
    box.style.overflow = "visible";

    const inner = document.createElement("div");
    inner.dataset.chartInner = "true";
    inner.style.width = `${Math.round(host.getBoundingClientRect().width)}px`;
    inner.style.transformOrigin = "top left";
    box.appendChild(inner);

    if (content) {
      const drawn = cloneWithComputedStyles(content);
      // The legend sits at the bottom edge of the chart and was being sliced in
      // half by a container that clips on screen. Nothing here relies on CSS
      // clipping for correctness -- the charts clip their plot area with SVG
      // clipPath, which this does not touch.
      drawn.querySelectorAll<HTMLElement>("*").forEach((el) => {
        if (el.style.overflow === "hidden") el.style.overflow = "visible";
      });
      inner.appendChild(drawn);
    } else {
      // A chart that never drew. Say so in the document rather than leaving a
      // silent gap the reader cannot interpret.
      inner.style.width = "100%";
      inner.textContent = "[chart unavailable]";
      inner.style.color = "#5C5F5E";
      inner.style.fontStyle = "italic";
    }
    target.replaceWith(box);
  });
}

/**
 * Scales each inlined chart up to the page width, once the stage is mounted.
 *
 * Has to run after mounting: the scale factor needs the outer box's laid-out
 * width, and the reserved height needs the chart's rendered height, neither of
 * which exists while the clone is detached.
 */
function scaleChartsToWidth(stage: HTMLElement) {
  stage.querySelectorAll<HTMLElement>("[data-chart-inner]").forEach((inner) => {
    const box = inner.parentElement;
    if (!box) return;
    const available = box.clientWidth;
    const natural = inner.offsetWidth;
    if (!available || !natural) return;

    applyChartScale(inner, box, chartScaleFactor(available, natural));
  });
}

/**
 * Scales one inlined chart and reserves the room it takes in the flow.
 *
 * The factor is recorded on the node because the height pass below scales the
 * same chart a second time, and it needs to compose with this factor rather
 * than replace it — reading it back off the transform would mean parsing a
 * matrix.
 */
function applyChartScale(inner: HTMLElement, box: HTMLElement, factor: number) {
  inner.dataset.chartScale = String(factor);
  inner.style.transform = `scale(${factor})`;
  // The transform does not affect layout, so the flow height must be reserved
  // explicitly or the chart overlaps whatever follows it.
  box.style.height = `${Math.round(inner.offsetHeight * factor)}px`;
  // A chart held back by the height cap is narrower than its card. Centre it,
  // rather than leaving it pinned left against a ragged gutter.
  const slack = box.clientWidth - inner.offsetWidth * factor;
  inner.style.marginLeft = slack > 1 ? `${Math.round(slack / 2)}px` : "0";
}

/**
 * Shrinks any chart card that came out taller than a page can safely hold.
 *
 * Fitting to the page width alone can leave a card half as tall again as it was
 * on screen: a chart drawn in the two-column grid is upscaled to fill a
 * single-column page, and the height follows the width. A card that big is the
 * one thing pageBreak cannot keep whole — it either overruns a page outright or
 * starts too near the top of one for moving the break to be worth it, and
 * either way the chart is cut through the middle, plot on one page and axis
 * labels and legend on the next. Capping the height puts both cases out of
 * reach.
 */
function fitCardsToPage(stage: HTMLElement, pageHeight: number) {
  const maxHeight = pageHeight * MAX_CARD_PAGE_FILL - CARD_HEIGHT_SLACK_PX;
  stage.querySelectorAll<HTMLElement>(".dc-chart-card").forEach((card) => {
    const inners = Array.from(
      card.querySelectorAll<HTMLElement>("[data-chart-inner]"),
    );
    if (inners.length === 0) return;
    const chartHeight = inners.reduce(
      (total, inner) =>
        total + (inner.parentElement?.getBoundingClientRect().height ?? 0),
      0,
    );
    const shrink = cardShrinkFactor(
      card.getBoundingClientRect().height,
      chartHeight,
      maxHeight,
    );
    if (shrink >= 1) return;
    inners.forEach((inner) => {
      const box = inner.parentElement;
      if (!box) return;
      const already = Number(inner.dataset.chartScale ?? 1);
      applyChartScale(inner, box, already * shrink);
    });
  });
}

/**
 * How much further to scale a card's charts so the card fits `maxHeight`.
 *
 * Only the charts shrink. The card's own chrome — its border, its padding,
 * anything sitting beside the chart — is a fixed cost that comes out of the
 * budget first. Returns 1 when the card already fits, and when the chrome alone
 * overruns the budget: no scale factor helps there, and shrinking the chart
 * towards nothing chasing it would be worse than the split it is avoiding.
 */
export function cardShrinkFactor(
  cardHeight: number,
  chartHeight: number,
  maxHeight: number,
): number {
  if (cardHeight <= maxHeight) return 1;
  if (chartHeight <= 0) return 1;
  const room = maxHeight - (cardHeight - chartHeight);
  if (room <= 0) return 1;
  return room / chartHeight;
}

/**
 * The page's content height, in the CSS pixels the stage is laid out in.
 *
 * Taken from the clone's laid-out width rather than PAGE_WIDTH_PX so it tracks
 * the ratio the canvas is actually sliced by: the page image is placed at the
 * full content width, whatever width the clone ended up taking.
 */
function pageHeightFor(clone: HTMLElement): number {
  const width = clone.getBoundingClientRect().width || PAGE_WIDTH_PX;
  return (width * A4_CONTENT_HEIGHT_MM) / A4_CONTENT_WIDTH_MM;
}

/**
 * The factor that fits a chart of `natural` width into `available` width.
 *
 * Scales in BOTH directions. An earlier version skipped any factor at or below
 * 1, on the theory that the card rules already handled an over-wide chart; they
 * do not, because the chart box is pinned to the chart's natural pixel width. A
 * chart drawn single-column on screen is wider than the page, so it was left
 * overhanging and the PDF cropped its right edge, shearing axis labels in half.
 *
 * Upscaling is capped so a small chart is not blown up absurdly; downscaling is
 * uncapped, because any amount of overflow is a crop.
 */
export function chartScaleFactor(available: number, natural: number): number {
  if (!available || !natural) return 1;
  return Math.min(available / natural, MAX_CHART_SCALE);
}

/**
 * Vertical bands, in canvas pixels, that should not be split across a page.
 *
 * Measured after mounting and scaling, relative to the clone's own top, then
 * multiplied by the rasterisation scale so the numbers are directly comparable
 * with canvas offsets during pagination.
 */
function unbreakableBands(clone: HTMLElement): Band[] {
  const origin = clone.getBoundingClientRect().top;
  const bands: Band[] = [];
  clone.querySelectorAll<HTMLElement>(".dc-chart-card, table").forEach((el) => {
    const rect = el.getBoundingClientRect();
    if (rect.height <= 0) return;
    bands.push({
      top: (rect.top - origin) * CANVAS_SCALE,
      bottom: (rect.bottom - origin) * CANVAS_SCALE,
    });
  });
  return bands.sort((a, b) => a.top - b.top);
}

/**
 * Chooses where to end a page.
 *
 * Slicing the canvas at fixed intervals cut straight through whatever happened
 * to be at the boundary -- a chart's plot ended one page and its axis labels
 * and legend began the next, sheared through the middle. If the natural break
 * falls inside a chart or a table, this moves the break up to that block's top
 * so the block starts the next page whole.
 *
 * Two cases deliberately fall through to the naive break: a block taller than
 * a page (it has to be split, there is nowhere else to put it), and a block
 * starting so close to the top of the page that moving the break would emit a
 * nearly empty page.
 *
 * A chart card can reach neither: fitCardsToPage caps it at MAX_CARD_PAGE_FILL
 * of the page precisely so it cannot. What is left here is for tables, which
 * have no scale factor to give.
 */
export interface Band {
  top: number;
  bottom: number;
}

export function pageBreak(
  offset: number,
  pageHeight: number,
  canvasHeight: number,
  bands: Band[],
): number {
  const naive = Math.min(pageHeight, canvasHeight - offset);
  const breakAt = offset + naive;
  if (breakAt >= canvasHeight) return naive;

  const straddled = bands.find((b) => b.top < breakAt && b.bottom > breakAt);
  if (!straddled) return naive;
  if (straddled.bottom - straddled.top > pageHeight) return naive;

  const shortened = straddled.top - offset;
  if (shortened < pageHeight * MIN_PAGE_FILL) return naive;
  return shortened;
}

/** Turns the question into a filesystem-safe basename. */
function fileNameFor(question: string): string {
  const slug = question
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return `${slug || "data-commons-answer"}.pdf`;
}

/**
 * Renders `target` to a PDF and downloads it.
 *
 * Deliberately not the browser print pipeline: window.print() can only open
 * the platform print dialog, and the requirement is a file that downloads on
 * click. The trade-off is that the page is rasterised, so the PDF has no
 * selectable text layer.
 *
 * Elements marked `data-non-print` are dropped, so the exported document is
 * the question and the answer without the follow-up questions or the UI
 * affordances around them — the same rule the print stylesheet applies.
 */
export async function downloadPdf(
  target: HTMLElement | null,
  question: string,
): Promise<void> {
  if (!target || !target.isConnected) return;

  // Nothing here may touch the live panel's layout. An earlier version laid it
  // out at page width first, so the chart components would redraw to fit; that
  // worked, but the card visibly jumped 832px -> 717px and back on every
  // export. The page-width layout happens entirely on the detached copy now,
  // and the charts are scaled to fit there instead of re-rendering.
  await whenChartsDrawn(target);
  await renderToPdf(target, question);
}

/**
 * Clones the panel, lays the copy out at page width, and writes the PDF.
 *
 * jsPDF and html2canvas are imported here rather than at module scope: together
 * they are ~600KB, needed only when someone actually exports, and statically
 * importing them tripled the initial bundle for a button most sessions never
 * press. Vite splits them into their own chunk, fetched on first export.
 */
async function renderToPdf(target: HTMLElement, question: string): Promise<void> {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import("html2canvas"),
    import("jspdf"),
  ]);

  // Lay the copy out at page width off-screen. It has to be rendered (not
  // display:none) for getComputedStyle and html2canvas to measure it, so it is
  // positioned far off-canvas instead of hidden.
  const stage = document.createElement("div");
  stage.style.position = "fixed";
  stage.style.left = "-10000px";
  stage.style.top = "0";
  stage.style.width = `${PAGE_WIDTH_PX}px`;
  stage.style.background = "#ffffff";
  stage.style.zIndex = "-1";

  const clone = target.cloneNode(true) as HTMLElement;
  clone.style.width = `${PAGE_WIDTH_PX}px`;
  clone.style.maxWidth = `${PAGE_WIDTH_PX}px`;
  clone.style.border = "0";
  clone.style.borderRadius = "0";
  clone.style.overflow = "visible";
  clone.style.background = "#ffffff";

  // Drop everything the printed document should not carry: the export buttons,
  // the provenance icon, the follow-up questions.
  clone.querySelectorAll('[data-non-print="true"]').forEach((el) => el.remove());

  // The question is the document's heading.
  //
  // index.css restyles it for print, but that rule lives in @media print and
  // this path never enters print media -- so the clone inherited the on-screen
  // one-line truncated title and the heading came out sliced in half. Applied
  // here instead, to the same element the print rule targets.
  clone.querySelectorAll<HTMLElement>(".print-question").forEach((q) => {
    q.style.whiteSpace = "normal";
    q.style.textOverflow = "clip";
    q.style.overflow = "visible";
    q.style.fontSize = "18px";
    q.style.lineHeight = "26px";
    q.style.fontWeight = "700";
    q.style.color = "#000000";
    // The row it sits in is sized for one line on screen; let it grow.
    const row = q.parentElement;
    if (row) {
      row.style.height = "auto";
      row.style.minHeight = "0";
      row.style.alignItems = "flex-start";
      row.style.padding = "0 0 12px 0";
      row.style.background = "#ffffff";
      row.style.borderBottom = "0";
    }
  });

  // Chart cards clip their contents on screen to keep rounded corners tidy.
  // In a document there is no viewport to fit, so let them grow instead --
  // otherwise the legend and the source row are cut off mid-line.
  clone.querySelectorAll<HTMLElement>(".dc-chart-card").forEach((card) => {
    card.style.height = "auto";
    card.style.maxHeight = "none";
    card.style.overflow = "visible";
    card.style.width = "100%";
    card.style.maxWidth = "100%";
    card.style.marginBottom = "16px";
  });
  clone.querySelectorAll<HTMLElement>(".dc-charts-container").forEach((grid) => {
    grid.style.display = "block";
  });

  inlineCharts(clone, target);

  stage.appendChild(clone);
  document.body.appendChild(stage);
  scaleChartsToWidth(stage);
  fitCardsToPage(stage, pageHeightFor(clone));

  try {
    const canvas = await html2canvas(clone, {
      scale: CANVAS_SCALE,
      backgroundColor: "#ffffff",
      useCORS: true,
      logging: false,
      windowWidth: PAGE_WIDTH_PX,
    });

    const pdf = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
    // How many canvas pixels fit on one page, at the scale the image is placed.
    const pxPerMm = canvas.width / A4_CONTENT_WIDTH_MM;
    const pageHeightPx = Math.floor(A4_CONTENT_HEIGHT_MM * pxPerMm);

    const bands = unbreakableBands(clone);
    let offset = 0;
    let first = true;
    while (offset < canvas.height) {
      const sliceHeight = pageBreak(offset, pageHeightPx, canvas.height, bands);
      if (sliceHeight <= 0) break;
      const slice = document.createElement("canvas");
      slice.width = canvas.width;
      slice.height = sliceHeight;
      const ctx = slice.getContext("2d");
      if (!ctx) break;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, slice.width, slice.height);
      ctx.drawImage(canvas, 0, offset, canvas.width, sliceHeight, 0, 0, canvas.width, sliceHeight);

      if (!first) pdf.addPage();
      pdf.addImage(
        // JPEG, not PNG: the same three pages came to ~18MB as PNG, which is
        // not a file anyone wants to receive. At this quality the difference
        // is not visible on chart labels.
        slice.toDataURL("image/jpeg", JPEG_QUALITY),
        "JPEG",
        MARGIN_MM,
        MARGIN_MM,
        A4_CONTENT_WIDTH_MM,
        sliceHeight / pxPerMm,
      );
      first = false;
      offset += sliceHeight;
    }

    pdf.save(fileNameFor(question));
  } finally {
    stage.remove();
  }
}
