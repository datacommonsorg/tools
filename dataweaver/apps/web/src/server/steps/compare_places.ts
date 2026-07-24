import { nanoid } from 'nanoid';
import { extractJson } from '~/functions/extract_json';
import { getGenAI } from '~/server/clients/gemini';
import { getServiceConfig, getSkillConfig } from '~/server/config';
import type {
  ComparisonChart,
  ComparisonResult,
  Insight,
  QueryResult,
} from '~/server/types';

// ─── Types ──────────────────────────────────────────────────────────────────

export interface PlaceSummary {
  placeName: string;
  placeDcid: string;
  variables: Array<{
    name: string;
    dcid: string;
    unit: string;
    latestValue: number;
    latestDate: string;
    minValue: number;
    maxValue: number;
    observationCount: number;
    dateRange: string;
  }>;
  insights: Insight[];
}

interface ComparePlacesParams {
  query: string;
  topic: string;
  summaries: PlaceSummary[];
}

interface ComparisonModelResponse {
  title?: string;
  coverage?: string;
  introduction?: string;
  insights?: Insight[];
  relatedQueries?: string[];
  charts?: ComparisonChart[];
}

// ─── Public API ─────────────────────────────────────────────────────────────

/** Serialize QueryResult objects into compact summaries for the comparison prompt. */
export const buildPlaceSummaries = (results: QueryResult[]): PlaceSummary[] => {
  return results.map((result) => {
    const placeName = result.entities[0]?.name ?? '';
    const placeDcid = result.entities[0]?.dcid ?? '';

    const variables = result.variables.map((v) => {
      const ts = result.timeSeries.find((t) => t.variableDcid === v.dcid);
      const observations = ts?.facets[0]?.observations ?? [];
      const unit = ts?.facets[0]?.unit ?? '';

      let latestValue = 0;
      let latestDate = '';
      let minValue = Number.POSITIVE_INFINITY;
      let maxValue = Number.NEGATIVE_INFINITY;

      for (const obs of observations) {
        if (!latestDate || obs.date > latestDate) {
          latestDate = obs.date;
          latestValue = obs.value;
        }
        if (obs.value < minValue) minValue = obs.value;
        if (obs.value > maxValue) maxValue = obs.value;
      }

      const earliestDate = ts?.facets[0]?.earliestDate ?? '';
      const latDate = ts?.facets[0]?.latestDate ?? '';
      const dateRange =
        earliestDate && latDate ? `${earliestDate} – ${latDate}` : '';

      return {
        name: v.name,
        dcid: v.dcid,
        unit,
        latestValue: observations.length > 0 ? latestValue : 0,
        latestDate,
        minValue: observations.length > 0 ? minValue : 0,
        maxValue: observations.length > 0 ? maxValue : 0,
        observationCount: observations.length,
        dateRange,
      };
    });

    return {
      placeName,
      placeDcid,
      variables,
      insights: result.insights ?? [],
    };
  });
};

/**
 * Run the Gemini comparison step for multiple places.
 * Returns a ComparisonResult with a Gemini-generated comparative narrative.
 */
export const comparePlaces = async (
  params: ComparePlacesParams,
): Promise<ComparisonResult> => {
  const { query, topic, summaries } = params;
  const config = getServiceConfig();
  const skill = getSkillConfig('data_comparison');
  const genAI = getGenAI();

  const placeNames = summaries.map((s) => s.placeName);
  const fallbackTitle =
    placeNames.length === 2
      ? `${topic} in ${placeNames[0]} vs ${placeNames[1]}`
      : `${topic} across ${placeNames.join(', ')}`;

  const userContent = `User query: "${query}"
Topic: "${topic}"
Places being compared: ${placeNames.join(', ')}

DATA SUMMARIES:
${JSON.stringify(summaries, null, 2)}`;

  const response = await genAI.models.generateContent({
    model: config.models.comparison,
    contents: userContent,
    config: { systemInstruction: skill.systemPrompt },
  });

  const responseText = response.text || '';
  const parsed = extractJson<ComparisonModelResponse>(responseText);

  return {
    id: nanoid(),
    title: parsed?.title || fallbackTitle,
    coverage: parsed?.coverage || undefined,
    introduction: parsed?.introduction || undefined,
    insights: parsed?.insights || undefined,
    relatedQueries: parsed?.relatedQueries || undefined,
    charts: parsed?.charts || undefined,
  };
};
