import type { ChartStyle } from '~/server/types';

// ─── Chart style change intent ────────────────────────────────────────────

const CHART_STYLE_MAP: Array<{ pattern: RegExp; style: ChartStyle }> = [
  { pattern: /\b(horizontal\s*bar)\b/i, style: 'bar-horizontal' },
  {
    pattern: /\b(bar\s*chart|bar\s*graph|vertical\s*bar|bar)\b/i,
    style: 'bar-vertical',
  },
  { pattern: /\b(line\s*chart|line\s*graph|line)\b/i, style: 'line' },
];

/**
 * When chart cards are already selected, bare directional/style words imply
 * the user wants to change the chart type (e.g. "make these horizontal").
 */
const CHART_STYLE_CONTEXTUAL_MAP: Array<{
  pattern: RegExp;
  style: ChartStyle;
}> = [
  { pattern: /\bhorizontal\b/i, style: 'bar-horizontal' },
  { pattern: /\bvertical\b/i, style: 'bar-vertical' },
  ...CHART_STYLE_MAP,
];

const UNSUPPORTED_CHART_KEYWORDS =
  /\b(pie\s*chart|pie|donut|doughnut|scatter|bubble|radar|area\s*chart|heatmap|treemap|histogram|waterfall|funnel|gauge|candlestick)\b/i;

const CHART_STYLE_INTENT =
  /\b(make\s*(this|these|it|them)|change\s*(this|these|it|them)?\s*to|switch\s*to|convert\s*to|turn\s*(this|these|it|them)\s*into|as\s*a)\b/i;

/**
 * Broader intent pattern — includes conversational prefixes like "let's
 * make", "can you make", "I want to make", etc.
 */
const CHART_STYLE_INTENT_BROAD =
  /\b(let'?s\s*(make|turn|switch|change)|can\s*(we|you)\s*(make|turn|switch|change)|i\s*want\s*(to\s*)?(make|turn|change)|make\s*(this|these|it|them)|change\s*(this|these|it|them)?\s*to|switch\s*(this|these|it|them)?\s*to|convert\s*to|turn\s*(this|these|it|them)\s*into|as\s*a)\b/i;

/**
 * Detect chart-style-change intent and extract the target style.
 * Returns the ChartStyle if valid, 'unsupported' for known-but-unsupported
 * chart types, or null if no chart-style-change intent was detected.
 *
 * When `hasChartSelection` is true, uses broader intent matching and allows
 * bare style words (e.g. "horizontal") since the chart context is implied.
 */
export const extractChartStyle = (
  prompt: string,
  hasChartSelection = false,
): ChartStyle | 'unsupported' | null => {
  const intentPattern = hasChartSelection
    ? CHART_STYLE_INTENT_BROAD
    : CHART_STYLE_INTENT;

  if (!intentPattern.test(prompt)) return null;

  const styleMap = hasChartSelection
    ? CHART_STYLE_CONTEXTUAL_MAP
    : CHART_STYLE_MAP;

  for (const { pattern, style } of styleMap) {
    if (pattern.test(prompt)) return style;
  }

  if (UNSUPPORTED_CHART_KEYWORDS.test(prompt)) return 'unsupported';

  return null;
};
