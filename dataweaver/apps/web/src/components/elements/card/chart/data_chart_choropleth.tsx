'use client';

import { type GeoGeometryObjects, geoPath } from 'd3-geo';
import { scaleLinear } from 'd3-scale';
import {
  type PointerEvent,
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type WheelEvent,
} from 'react';
import type {
  GeoJsonFeature,
  GeoJsonFeatureCollection,
} from '~/app/api/geo/route';
import { IconMinus } from '~/components/primitives/icons/minus';
import { IconPlus } from '~/components/primitives/icons/plus';
import type { ChartSeries } from './chart';
import { ChartContainer } from './chart_container';
import s from './data_chart_choropleth.module.scss';
import {
  fetchGeoJson,
  getCachedGeoJson,
  hasCompleteGeoJson,
  resolveGeoCacheKey,
} from './geo_service';
import { getMapProjection } from './map_projection';
import { SCALE_MONOTONIC } from './palette';
import { SliderTime } from './slider_time';

export interface DataChartChoroplethProps {
  series: ChartSeries[];
  parentPlaceDcid?: string;
  onUnavailable?: () => void;
  onEntityClick?: (entityDcid: string, label: string) => void;
}

interface Transform {
  k: number;
  x: number;
  y: number;
}

interface ChoroplethHoverInfo {
  dcid: string;
  name: string;
  value: number | null;
  unit?: string;
  x: number;
  y: number;
  containerWidth?: number;
  containerHeight?: number;
}

interface ChoroplethMapCanvasProps {
  width: number;
  height: number;
  uniqueFeatures: GeoJsonFeature[];
  parentFeature?: GeoJsonFeature;
  enclosingDcid?: string;
  entityKeys: string[];
  transform: Transform;
  valueMap: Map<string, number>;
  metaMap: Map<string, { label: string; unit?: string }>;
  colorScale: (val: number) => string;
  unit: string;
  isDragging: boolean;
  series: ChartSeries[];
  svgRef: RefObject<SVGSVGElement | null>;
  dragMovedRef: RefObject<boolean>;
  onWheel: (e: WheelEvent<SVGSVGElement>) => void;
  onPointerDown: (e: PointerEvent<SVGSVGElement>) => void;
  onPointerMove: (e: PointerEvent<SVGSVGElement>) => void;
  onPointerUp: (e: PointerEvent<SVGSVGElement>) => void;
  onPointerLeave: () => void;
  onHover: (hover: ChoroplethHoverInfo | null) => void;
  onEntityClick?: (entityDcid: string, label: string) => void;
}

const ChoroplethMapCanvas = ({
  width,
  height,
  uniqueFeatures,
  parentFeature,
  enclosingDcid,
  entityKeys,
  transform,
  valueMap,
  metaMap,
  colorScale,
  unit,
  isDragging,
  series,
  svgRef,
  dragMovedRef,
  onWheel,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerLeave,
  onHover,
  onEntityClick,
}: ChoroplethMapCanvasProps) => {
  // Memoize path computation and projection fitting to avoid heavy recalculation during pan/zoom/hover
  const mapPaths = useMemo(() => {
    const { projection: proj, isMapFitted } = getMapProjection(
      enclosingDcid,
      width,
      height,
      entityKeys,
    );
    const pathGenerator = geoPath().projection(proj);

    if (!isMapFitted) {
      proj.scale(1).translate([0, 0]);

      const targetGeo = parentFeature ?? {
        type: 'FeatureCollection',
        features: uniqueFeatures,
      };

      const b = pathGenerator.bounds(
        targetGeo as unknown as GeoGeometryObjects,
      );

      if (
        b &&
        Number.isFinite(b[0][0]) &&
        Number.isFinite(b[0][1]) &&
        Number.isFinite(b[1][0]) &&
        Number.isFinite(b[1][1])
      ) {
        const dx = b[1][0] - b[0][0];
        const dy = b[1][1] - b[0][1];

        if (dx > 0 && dy > 0) {
          const scale = 0.92 / Math.max(dx / width, dy / height);
          const translateX = (width - scale * (b[1][0] + b[0][0])) / 2;
          const translateY = (height - scale * (b[1][1] + b[0][1])) / 2;
          proj.scale(scale).translate([translateX, translateY]);
        }
      }
    }

    const paths: Array<{ dcid: string; pathString: string }> = [];
    for (const feature of uniqueFeatures) {
      const pathString = pathGenerator(
        feature.geometry as unknown as GeoGeometryObjects,
      );
      if (pathString) {
        paths.push({ dcid: feature.id, pathString });
      }
    }
    return paths;
  }, [uniqueFeatures, parentFeature, enclosingDcid, entityKeys, width, height]);

  return (
    <svg
      ref={svgRef}
      role="img"
      aria-label="Choropleth map"
      className={s['map-svg']}
      viewBox={`0 0 ${width} ${height}`}
      onWheel={onWheel}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerLeave}
    >
      <title>Choropleth map</title>
      <g
        transform={`translate(${transform.x}, ${transform.y}) scale(${transform.k})`}
      >
        {mapPaths.map(({ dcid, pathString }) => {
          const val = valueMap.get(dcid);
          const hasVal = val !== undefined && val !== null;
          const meta = metaMap.get(dcid);
          const name = meta?.label || dcid;
          const fillColor = hasVal ? colorScale(val) : undefined;

          return (
            <path
              key={dcid}
              d={pathString}
              className={hasVal ? s['feature-path'] : s['feature-no-data']}
              style={fillColor ? { fill: fillColor } : undefined}
              onPointerDown={(e) => {
                e.stopPropagation();
              }}
              onClick={(e) => {
                e.stopPropagation();
                if (dragMovedRef.current) return;
                if (hasVal || series.some((s) => s.key === dcid)) {
                  onEntityClick?.(dcid, name);
                }
              }}
              onPointerMove={(e) => {
                if (isDragging) return;
                const rect = e.currentTarget
                  .closest('svg')
                  ?.getBoundingClientRect();
                if (rect) {
                  onHover({
                    dcid,
                    name,
                    value: hasVal ? val : null,
                    unit: meta?.unit || unit,
                    x: e.clientX - rect.left,
                    y: e.clientY - rect.top,
                    containerWidth: rect.width,
                    containerHeight: rect.height,
                  });
                }
              }}
              onPointerLeave={() => {
                if (!isDragging) onHover(null);
              }}
            >
              <title>
                {`${name}: ${hasVal ? `${val.toLocaleString()} ${meta?.unit || unit}` : 'No data'}`}
              </title>
            </path>
          );
        })}
      </g>
    </svg>
  );
};

export const DataChartChoropleth = ({
  series,
  parentPlaceDcid,
  onUnavailable,
  onEntityClick,
}: DataChartChoroplethProps) => {
  const dates = useMemo(() => {
    const set = new Set<string>();
    for (const s of series) {
      for (const d of s.data) {
        set.add(d.date);
      }
    }
    return Array.from(set).sort();
  }, [series]);

  const [selectedDate, setSelectedDate] = useState<string>(
    () => dates[dates.length - 1] ?? '',
  );

  useEffect(() => {
    if (dates.length > 0 && (!selectedDate || !dates.includes(selectedDate))) {
      setSelectedDate(dates[dates.length - 1] ?? '');
    }
  }, [dates, selectedDate]);

  const validEntityKeys = useMemo(() => {
    return series
      .map((s) => s.key)
      .filter((k) => k && k !== 'default')
      .sort();
  }, [series]);

  const cacheKey = useMemo(() => {
    return resolveGeoCacheKey(parentPlaceDcid, validEntityKeys);
  }, [parentPlaceDcid, validEntityKeys]);

  const [geoJson, setGeoJson] = useState<GeoJsonFeatureCollection | null>(
    () => getCachedGeoJson(cacheKey) ?? null,
  );
  const [isLoadingGeo, setIsLoadingGeo] = useState<boolean>(!geoJson);
  const [geoError, setGeoError] = useState<boolean>(false);

  useEffect(() => {
    let isCurrent = true;

    if (!cacheKey) {
      setIsLoadingGeo(false);
      setGeoError(true);
      onUnavailable?.();
      return;
    }

    const cached = getCachedGeoJson(cacheKey);
    if (cached) {
      const isComplete = hasCompleteGeoJson(cached, validEntityKeys);
      if (!isComplete) {
        setGeoError(true);
        onUnavailable?.();
      } else {
        setGeoJson(cached);
        setGeoError(false);
      }
      setIsLoadingGeo(false);
      return;
    }

    setIsLoadingGeo(true);
    setGeoError(false);

    fetchGeoJson(parentPlaceDcid, validEntityKeys)
      .then((data) => {
        if (!isCurrent) return;
        const isComplete = hasCompleteGeoJson(data, validEntityKeys);
        if (!isComplete) {
          setGeoError(true);
          onUnavailable?.();
        } else {
          setGeoJson(data);
        }
        setIsLoadingGeo(false);
      })
      .catch((err) => {
        if (!isCurrent) return;
        console.warn('Failed to load choropleth boundaries:', err);
        setGeoError(true);
        setIsLoadingGeo(false);
        onUnavailable?.();
      });

    return () => {
      isCurrent = false;
    };
  }, [cacheKey, parentPlaceDcid, validEntityKeys, onUnavailable]);

  const [transform, setTransform] = useState<Transform>({ k: 1, x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{
    x: number;
    y: number;
    tx: number;
    ty: number;
  } | null>(null);
  const dragMovedRef = useRef(false);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const resetZoom = useCallback(() => {
    setTransform({ k: 1, x: 0, y: 0 });
  }, []);

  const zoomIn = useCallback(() => {
    setTransform((prev) => {
      const nextK = Math.min(8, prev.k * 1.4);
      return { ...prev, k: nextK };
    });
  }, []);

  const zoomOut = useCallback(() => {
    setTransform((prev) => {
      const nextK = Math.max(1, prev.k / 1.4);
      if (nextK === 1) return { k: 1, x: 0, y: 0 };
      return { ...prev, k: nextK };
    });
  }, []);

  const handleWheel = useCallback((e: WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;

    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    setTransform((prev) => {
      const nextK = Math.min(8, Math.max(1, prev.k * zoomFactor));
      if (nextK === 1) return { k: 1, x: 0, y: 0 };

      const nextX = mouseX - ((mouseX - prev.x) / prev.k) * nextK;
      const nextY = mouseY - ((mouseY - prev.y) / prev.k) * nextK;
      return { k: nextK, x: nextX, y: nextY };
    });
  }, []);

  const handlePointerDown = useCallback(
    (e: PointerEvent<SVGSVGElement>) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      dragMovedRef.current = false;
      dragStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        tx: transform.x,
        ty: transform.y,
      };
    },
    [transform],
  );

  const handlePointerMove = useCallback(
    (e: PointerEvent<SVGSVGElement>) => {
      const start = dragStartRef.current;
      if (!start) return;
      const dx = e.clientX - start.x;
      const dy = e.clientY - start.y;
      if (!isDragging && Math.hypot(dx, dy) > 4) {
        setIsDragging(true);
        dragMovedRef.current = true;
        try {
          e.currentTarget.setPointerCapture(e.pointerId);
        } catch {
          // Ignore
        }
      }
      if (isDragging || dragMovedRef.current) {
        setTransform((prev) => ({
          ...prev,
          x: start.tx + dx,
          y: start.ty + dy,
        }));
      }
    },
    [isDragging],
  );

  const handlePointerUp = useCallback(
    (e: PointerEvent<SVGSVGElement>) => {
      e.stopPropagation();
      if (isDragging) {
        setIsDragging(false);
        try {
          e.currentTarget.releasePointerCapture(e.pointerId);
        } catch {
          // Ignore pointer capture release error if already lost
        }
      }
      dragStartRef.current = null;
    },
    [isDragging],
  );

  const valueMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const s of series) {
      const obs = s.data.find((d) => d.date === selectedDate);
      if (obs !== undefined) {
        map.set(s.key, obs.value);
      }
    }
    return map;
  }, [series, selectedDate]);

  const metaMap = useMemo(() => {
    const map = new Map<string, { label: string; unit?: string }>();
    for (const s of series) {
      map.set(s.key, { label: s.label, unit: s.unit });
    }
    return map;
  }, [series]);

  const [minVal, maxVal] = useMemo(() => {
    const vals = series.flatMap((s) => s.data.map((d) => d.value));
    if (vals.length === 0) return [0, 100];
    return [Math.min(...vals), Math.max(...vals)];
  }, [series]);

  const activeScaleStops = SCALE_MONOTONIC[0];

  const colorScale = useMemo(() => {
    const max = maxVal === minVal ? maxVal + 1 : maxVal;
    const step = (max - minVal) / (activeScaleStops.length - 1);
    const domain = activeScaleStops.map((_, i) => minVal + i * step);

    return scaleLinear<string>()
      .domain(domain)
      .range(activeScaleStops as unknown as string[])
      .clamp(true);
  }, [minVal, maxVal]);

  const [hovered, setHovered] = useState<ChoroplethHoverInfo | null>(null);

  const unit = series[0]?.unit ?? '';
  const hasFeatures = !!geoJson && geoJson.features.length > 0;
  const isZoomedOrPanned =
    transform.k !== 1 || transform.x !== 0 || transform.y !== 0;

  const uniqueFeatures = useMemo(() => {
    if (!geoJson?.features) return [];
    const seen = new Set<string>();
    const list: GeoJsonFeature[] = [];
    for (const f of geoJson.features) {
      if (!seen.has(f.id)) {
        seen.add(f.id);
        list.push(f);
      }
    }
    if (list.length > 1 && geoJson.parentDcid) {
      return list.filter((f) => f.id !== geoJson.parentDcid);
    }
    return list;
  }, [geoJson]);

  return (
    <div className={s.container}>
      <div className={s['map-container']}>
        {isLoadingGeo ? (
          <div className={s['loading-container']}>
            <span>Loading map boundaries...</span>
          </div>
        ) : geoError || !hasFeatures ? (
          <div className={s['empty-container']}>
            <span>Map boundaries not available for these entities</span>
          </div>
        ) : (
          <>
            <div className={s['zoom-controls']}>
              <button
                type="button"
                className={s['button-zoom']}
                onClick={zoomIn}
                aria-label="Zoom in"
                title="Zoom in"
              >
                <IconPlus />
              </button>
              <button
                type="button"
                className={s['button-zoom']}
                onClick={zoomOut}
                aria-label="Zoom out"
                title="Zoom out"
              >
                <IconMinus />
              </button>
              {isZoomedOrPanned && (
                <button
                  type="button"
                  className={s['button-zoom']}
                  onClick={resetZoom}
                  aria-label="Reset zoom and view"
                  title="Reset view"
                >
                  1:1
                </button>
              )}
            </div>

            <ChartContainer aspect={1.22}>
              {(width, height) => (
                <ChoroplethMapCanvas
                  width={width}
                  height={height}
                  uniqueFeatures={uniqueFeatures}
                  parentFeature={geoJson.parentFeature}
                  enclosingDcid={geoJson.parentDcid || parentPlaceDcid}
                  entityKeys={validEntityKeys}
                  transform={transform}
                  valueMap={valueMap}
                  metaMap={metaMap}
                  colorScale={colorScale}
                  unit={unit}
                  isDragging={isDragging}
                  series={series}
                  svgRef={svgRef}
                  dragMovedRef={dragMovedRef}
                  onWheel={handleWheel}
                  onPointerDown={handlePointerDown}
                  onPointerMove={handlePointerMove}
                  onPointerUp={handlePointerUp}
                  onPointerLeave={() => {
                    setHovered(null);
                    if (isDragging) {
                      setIsDragging(false);
                    }
                    dragStartRef.current = null;
                  }}
                  onHover={setHovered}
                  onEntityClick={onEntityClick}
                />
              )}
            </ChartContainer>
          </>
        )}

        {hovered && !isDragging && (
          <div
            className={[
              s.tooltip,
              hovered.y < 60 ? s['tooltip-align-bottom'] : '',
              hovered.x < 80 ? s['tooltip-align-left'] : '',
              hovered.containerWidth !== undefined &&
              hovered.x > hovered.containerWidth - 80
                ? s['tooltip-align-right']
                : '',
            ]
              .filter(Boolean)
              .join(' ')}
            style={{ left: hovered.x, top: hovered.y }}
          >
            <div className={s['tooltip-title']}>{hovered.name}</div>
            {hovered.value !== null ? (
              <>
                <div className={s['tooltip-value']}>
                  {`${hovered.value.toLocaleString()}${hovered.unit ? ` ${hovered.unit}` : ''}`}
                </div>
                {onEntityClick && (
                  <div className={s['tooltip-hint']}>
                    Click to view time series
                  </div>
                )}
              </>
            ) : (
              <div className={s['tooltip-no-data']}>
                {`No data for ${selectedDate}`}
              </div>
            )}
          </div>
        )}
      </div>

      <div className={s['legend-container']}>
        <span>
          {minVal.toLocaleString()}
          {unit ? ` ${unit}` : ''}
        </span>
        <div
          className={s['legend-gradient']}
          style={{
            background: `linear-gradient(to right, ${activeScaleStops.join(', ')})`,
          }}
        />
        <span>
          {maxVal.toLocaleString()}
          {unit ? ` ${unit}` : ''}
        </span>
      </div>

      <SliderTime
        dates={dates}
        selectedDate={selectedDate}
        onSelectDate={setSelectedDate}
      />
    </div>
  );
};
