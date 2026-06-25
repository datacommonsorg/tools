/**
 * @fileoverview Chart tile component that parses chart configuration and renders
 * Recharts visualizations (lines or bars) inside cards.
 */

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchPoint,
  fetchSeries,
  pickSourceFromFacets,
  pivotPointToRowsByPlace,
  pivotSeriesToRows,
  prettyPlaceName,
  prettyVariableName,
  type ChartRow,
  type PointResponse,
  type SeriesResponse,
} from "../api/dc_observations";
import type {
  ChartConfig,
  ChartItem,
  ProvenanceItem,
} from "../hooks/use_sse_chat";

// TODO(followup): Split this large file into multiple files under a charts/ subfolder
// (e.g. charts/chart_tile.tsx, charts/chart_card.tsx, charts/chart_graph.tsx, etc.)
// to improve readability and code organization. Also, extract inline styling to a template/theme file.

/**
 * Visual spec (Figma node 3427-16743) — owned by us end-to-end, no DC
 * web components. Charts are rendered with Recharts so every pixel of the
 * chart interior is themable to match Figma exactly.
 */
interface TileChartProps {
  config: ChartConfig;
  provenance?: ProvenanceItem[];
}

const MAX_CHARTS = 3;

// Figma tokens
const COLOR_BORDER = "#E3E3E3";
const COLOR_TITLE = "#3B3B3B";
const COLOR_LABEL = "#212529";
const COLOR_LINK = "#175C75";
const COLOR_AXIS = "#6B7280";
const COLOR_GRID = "#E3E3E3";
const FONT_STACK = '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

// Multi-series palette — primary first, then complementary hues that
// remain readable on white. All chosen to feel native to the Figma
// palette ("AI Dark Blue" sits at index 0).
const SERIES_COLORS = [
  "#175C75",
  "#1A73E8",
  "#0F9D58",
  "#F29900",
  "#D93025",
  "#9334E6",
];

/**
 * TileChart component parses chart configurations and renders up to three
 * visualization cards inside a layout grid.
 */
export function TileChart({ config, provenance }: TileChartProps) {
  if (!config || !config.should_render || config.hide_charts) {
    return null;
  }

  // Modern format: charts[] array. Legacy fallback: treat the config
  // itself as a single chart if it has variable_dcids at the top level.
  let charts: ChartItem[] | undefined = config.charts;
  if (!charts || !Array.isArray(charts) || charts.length === 0) {
    if (config.variable_dcids && config.variable_dcids.length > 0) {
      charts = [
        {
          viz_type: config.viz_type ?? "line",
          title: config.title,
          variable_dcids: config.variable_dcids,
          place_dcids: config.place_dcids,
          parent_place: config.parent_place,
          child_place_type: config.child_place_type,
          date: config.date,
        },
      ];
    } else {
      return null;
    }
  }

  const toRender = charts
    .slice(0, MAX_CHARTS)
    .filter((c) => c.variable_dcids && c.variable_dcids.length > 0);
  if (toRender.length === 0) {
    return null;
  }

  // Figma node 3427-16740 "Charts": 2-column grid, gap 52px, each child
  // chart card fills its column (Figma fixed width is 383, but we let the
  // grid track size so it scales with viewport).
  const isGrid = toRender.length >= 2;
  return (
    <div
      className="dc-charts-container mt-4"
      style={{
        display: "grid",
        gridTemplateColumns: isGrid
          ? "repeat(auto-fit, minmax(320px, 1fr))"
          : "1fr",
        gap: 24,
      }}
    >
      {toRender.map((c, i) => (
        <ChartCard
          key={i}
          chart={c}
          fallbackSource={provenance?.[i] ?? provenance?.[0]}
        />
      ))}
    </div>
  );
}

function ChartCard({
  chart,
  fallbackSource,
}: {
  chart: ChartItem;
  fallbackSource?: ProvenanceItem;
}) {
  const title = chart.title ?? "Data Visualization";
  const data = useChartData(chart);
  const source = data.source ?? fallbackSource;

  const handleDownload = () => {
    if (!data.rows || data.rows.length === 0) {
      return;
    }
    downloadCsv(filenameFor(title), data.rows, data.variableKeys ?? []);
  };

  return (
    <div
      className="dc-chart-card overflow-hidden bg-white"
      style={{ border: `1px solid ${COLOR_BORDER}`, borderRadius: 8 }}
    >
      {/* Title + source caption */}
      <div className="px-6 pt-6 pb-2">
        <h4
          className="text-base leading-6 font-medium"
          style={{ color: COLOR_TITLE, fontFamily: FONT_STACK }}
        >
          {title}
        </h4>
        {source ? (
          <div
            className="mt-1 flex items-center flex-wrap"
            style={{
              fontFamily: FONT_STACK,
              fontSize: 11,
              lineHeight: "16px",
              letterSpacing: "0.0091em",
              fontWeight: 500,
            }}
          >
            <span style={{ color: COLOR_LABEL }}>Source:&nbsp;</span>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
              style={{ color: COLOR_LINK }}
            >
              {prettySourceName(source)}
            </a>
            <span style={{ color: COLOR_LABEL }}>&nbsp;•&nbsp;</span>
            <button
              type="button"
              className="hover:underline bg-transparent border-0 p-0 cursor-pointer"
              style={{ color: COLOR_LINK, font: "inherit" }}
              onClick={() => {
                if (source.url) {
                  window.open(source.url, "_blank", "noopener");
                }
              }}
            >
              About this data
            </button>
          </div>
        ) : null}
      </div>

      {/* Chart area */}
      <div className="dc-chart-area px-6 pb-4">
        <div style={{ width: "100%", height: 280 }}>
          {data.loading ? (
            <ChartSkeleton />
          ) : data.error ? (
            <ChartMessage tone="error" text={`Chart unavailable: ${data.error}`} />
          ) : !data.rows || data.rows.length === 0 ? (
            <ChartMessage tone="muted" text="No data available." />
          ) : (
            <ChartGraph chart={chart} rows={data.rows} variableKeys={data.variableKeys ?? []} />
          )}
        </div>
      </div>

      {/* Footer with Download */}
      <div
        className="flex items-center justify-start px-6 py-4"
        style={{ borderTop: `1px solid ${COLOR_BORDER}` }}
      >
        <button
          type="button"
          onClick={handleDownload}
          disabled={!data.rows || data.rows.length === 0}
          className="flex items-center gap-2 hover:underline bg-transparent border-0 p-0 cursor-pointer disabled:opacity-50"
          style={{
            color: COLOR_LINK,
            fontFamily: FONT_STACK,
            fontSize: 14,
            lineHeight: "20px",
            fontWeight: 500,
          }}
          aria-label="Download chart data as CSV"
        >
          <DownloadIcon />
          <span>Download</span>
        </button>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Recharts renderers
// ───────────────────────────────────────────────────────────────

function ChartGraph({
  chart,
  rows,
  variableKeys,
}: {
  chart: ChartItem;
  rows: ChartRow[];
  variableKeys: string[];
}) {
  const isComparison = variableKeys.length > 1;

  switch (chart.viz_type) {
    case "bar": {
      // Single-date bar across places, or time-series bar — we plot
      // whichever the data shape is. In both cases x is `date` (which is
      // a place name when we pivoted by place).
      return (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={COLOR_GRID} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="date" {...axisProps()} interval="preserveStartEnd" />
            <YAxis {...axisProps()} tickFormatter={compactNumber} width={56} />
            <Tooltip {...tooltipProps()} />
            {isComparison && <Legend {...legendProps()} />}
            {variableKeys.map((v, i) => (
              <Bar
                key={v}
                dataKey={v}
                name={prettyVariableName(v)}
                fill={SERIES_COLORS[i % SERIES_COLORS.length]}
                radius={[4, 4, 0, 0]}
                maxBarSize={48}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      );
    }

    case "ranking": {
      // Horizontal bar, sorted desc, top 10.
      const sorted = [...rows]
        .filter((r) => typeof r[variableKeys[0]] === "number")
        .sort(
          (a, b) =>
            ((b[variableKeys[0]] as number) ?? 0) -
            ((a[variableKeys[0]] as number) ?? 0),
        )
        .slice(0, 10);
      return (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={sorted}
            layout="vertical"
            margin={{ top: 4, right: 16, left: 16, bottom: 0 }}
          >
            <CartesianGrid stroke={COLOR_GRID} strokeDasharray="2 4" horizontal={false} />
            <XAxis type="number" {...axisProps()} tickFormatter={compactNumber} />
            <YAxis
              type="category"
              dataKey="date"
              {...axisProps()}
              width={130}
              tick={{ ...axisTickStyle(), textAnchor: "end" }}
            />
            <Tooltip {...tooltipProps()} />
            <Bar
              dataKey={variableKeys[0]}
              name={prettyVariableName(variableKeys[0])}
              fill={SERIES_COLORS[0]}
              radius={[0, 4, 4, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      );
    }

    case "line":
    default:
      return (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={COLOR_GRID} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="date" {...axisProps()} interval="preserveStartEnd" />
            <YAxis {...axisProps()} tickFormatter={compactNumber} width={56} />
            <Tooltip {...tooltipProps()} />
            {isComparison && <Legend {...legendProps()} />}
            {variableKeys.map((v, i) => (
              <Line
                key={v}
                type="monotone"
                dataKey={v}
                name={prettyVariableName(v)}
                stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      );
  }
}

// ───────────────────────────────────────────────────────────────
// Data fetching
// ───────────────────────────────────────────────────────────────

type ChartDataState = {
  loading: boolean;
  rows: ChartRow[] | null;
  variableKeys: string[] | null;
  source?: ProvenanceItem;
  error?: string;
};

function useChartData(chart: ChartItem): ChartDataState {
  const [state, setState] = useState<ChartDataState>({
    loading: true,
    rows: null,
    variableKeys: null,
  });
  // Stringified inputs so the effect only re-fires when chart contents
  // actually change — not on every parent re-render (which would abort
  // the in-flight fetch via the cleanup function and start a new one,
  // leaving the spinner spinning forever).
  const key = JSON.stringify({
    v: chart.variable_dcids,
    p: chart.place_dcids,
    t: chart.viz_type,
    d: chart.date,
    pp: chart.parent_place,
    cpt: chart.child_place_type,
  });

  useEffect(() => {
    const ac = new AbortController();
    setState({ loading: true, rows: null, variableKeys: null });

    (async () => {
      try {
        const result = await loadChart(chart, ac.signal);
        setState({ loading: false, ...result });
      } catch (e: unknown) {
        if ((e as { name?: string })?.name === "AbortError") {
          return;
        }
        const msg = e instanceof Error ? e.message : String(e);
        setState({ loading: false, rows: null, variableKeys: null, error: msg });
      }
    })();

    return () => ac.abort();
    // chart is read inside but its identity is irrelevant — `key` is the
    // canonical change signal. Intentional dep omission.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state;
}

async function loadChart(
  chart: ChartItem,
  signal: AbortSignal,
): Promise<Omit<ChartDataState, "loading">> {
  const variables = chart.variable_dcids.filter(Boolean);
  const places =
    chart.place_dcids && chart.place_dcids.length > 0
      ? chart.place_dcids
      : ["country/USA"];

  // For ranking, ideally we'd query /api/observations/point across all
  // children of parent_place. Without a child-enumeration endpoint
  // available client-side, we fall back to whatever places the agent
  // gave us. If only one place is supplied the ranking will be a
  // degenerate single bar — better than crashing.
  if (chart.viz_type === "ranking" && places.length === 1) {
    // No child enumeration → fall back to time-series style render
    // with a single bar over years for the supplied place.
    const json = (await fetchSeries(variables, places, signal)) as SeriesResponse;
    const rows = pivotSeriesToRows(json, variables, places[0]);
    return {
      rows: rows.map((r) => ({ ...r, date: prettyPlaceName(places[0]) })),
      variableKeys: variables,
      source: pickSourceFromFacets(json),
    };
  }

  // Bar by place (single variable, single date): use point endpoint
  if (chart.viz_type === "bar" && places.length > 1 && chart.date) {
    const json = (await fetchPoint(
      variables,
      places,
      chart.date,
      signal,
    )) as PointResponse;
    const byPlace = pivotPointToRowsByPlace(json, variables[0]);
    return {
      rows: byPlace.map((r) => ({
        date: prettyPlaceName(r.place),
        [variables[0]]: r.value,
      })),
      variableKeys: [variables[0]],
      source: pickSourceFromFacets(json),
    };
  }

  // Default: time-series for one place
  const json = (await fetchSeries(variables, places, signal)) as SeriesResponse;
  const rows = pivotSeriesToRows(json, variables, places[0]);
  return {
    rows,
    variableKeys: variables,
    source: pickSourceFromFacets(json),
  };
}

// ───────────────────────────────────────────────────────────────
// Shared chart styling helpers
// ───────────────────────────────────────────────────────────────

function axisTickStyle() {
  return {
    fontFamily: FONT_STACK,
    fontSize: 11,
    fill: COLOR_AXIS,
  };
}

function axisProps() {
  return {
    stroke: COLOR_AXIS,
    tickLine: false,
    axisLine: { stroke: COLOR_GRID },
    tick: axisTickStyle(),
  };
}

function tooltipProps() {
  return {
    contentStyle: {
      fontFamily: FONT_STACK,
      fontSize: 12,
      border: `1px solid ${COLOR_BORDER}`,
      borderRadius: 8,
      boxShadow: "0 2px 6px rgba(60, 64, 67, 0.15)",
    },
    labelStyle: { color: COLOR_TITLE, fontWeight: 500 },
    cursor: { stroke: COLOR_AXIS, strokeDasharray: "2 4" },
  };
}

function legendProps() {
  return {
    wrapperStyle: {
      fontFamily: FONT_STACK,
      fontSize: 11,
      paddingTop: 8,
    },
    iconType: "circle" as const,
  };
}

function compactNumber(n: number): string {
  if (n === 0) {
    return "0";
  }
  const abs = Math.abs(n);
  if (abs >= 1e12) {
    return (n / 1e12).toFixed(1).replace(/\.0$/, "") + "T";
  }
  if (abs >= 1e9) {
    return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
  }
  if (abs >= 1e6) {
    return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  }
  if (abs >= 1e3) {
    return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  }
  return String(Math.round(n));
}

// ───────────────────────────────────────────────────────────────
// Small UI helpers
// ───────────────────────────────────────────────────────────────

function ChartSkeleton() {
  return (
    <div
      className="w-full h-full rounded-md flex items-center justify-center"
      style={{ backgroundColor: "#FAFAFA" }}
    >
      <div
        style={{
          width: 24,
          height: 24,
          border: `2px solid ${COLOR_GRID}`,
          borderTopColor: COLOR_LINK,
          borderRadius: "50%",
          animation: "dcSpin 1s linear infinite",
        }}
      />
      <style>{`@keyframes dcSpin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function ChartMessage({
  tone,
  text,
}: {
  tone: "error" | "muted";
  text: string;
}) {
  return (
    <div
      className="w-full h-full flex items-center justify-center rounded-md"
      style={{
        backgroundColor: tone === "error" ? "#FEF6F5" : "#FAFAFA",
        color: tone === "error" ? "#C5221F" : COLOR_AXIS,
        fontFamily: FONT_STACK,
        fontSize: 13,
        padding: 16,
        textAlign: "center",
      }}
    >
      {text}
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg
      width={24}
      height={24}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z" />
    </svg>
  );
}

function prettySourceName(source: ProvenanceItem): string {
  if (source.name && source.name.length <= 64) {
    return source.name;
  }
  try {
    return new URL(source.url).host;
  } catch {
    return source.name || source.url || "source";
  }
}

function filenameFor(title: string): string {
  return (
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "")
      .slice(0, 60) || "chart"
  ) + ".csv";
}

function downloadCsv(filename: string, rows: ChartRow[], keys: string[]) {
  const header = ["date", ...keys];
  const body = rows.map((r) =>
    header
      .map((k) => {
        const v = r[k];
        if (v === undefined || v === null) {
          return "";
        }
        const s = String(v);
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
      })
      .join(","),
  );
  const csv = [header.join(","), ...body].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
