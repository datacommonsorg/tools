import { IconCopy } from '~/components/primitives/icons/copy';
import { IconDownload } from '~/components/primitives/icons/download';
import { IconNarrative } from '~/components/primitives/icons/narrative';
import { IconShapes } from '~/components/primitives/icons/shapes';

/** The available export formats. */
// TODO: Implement the actual export functionality for each of these formats
export const EXPORT_OPTIONS = [
  {
    key: 'api-request-code',
    title: 'API Request Code',
    description:
      'Get the REST V2 API code to access the data from the selected cards in JSON or Python format.',
    action: 'Generate API Code',
    icon: IconCopy,
  },
  {
    key: 'csv',
    title: 'CSV',
    description:
      'Download the structured raw data from the selected cards as a CSV spreadsheet.',
    action: 'Download CSVs',
    icon: IconDownload,
  },
  {
    key: 'ai-narrative',
    title: 'AI Narrative',
    description:
      'Generate a text-based analytical summary from selected cards.',
    action: 'Generate narrative',
    icon: IconNarrative,
  },
  {
    key: 'ai-infographic',
    title: 'AI Infographic',
    description:
      'Transform the data and charts from the selected cards into a structured visual presentation.',
    action: 'Generate with Gemini',
    icon: IconShapes,
  },
  {
    key: 'svg',
    title: 'SVG',
    description:
      'Export the selected charts as high-resolution, scalable vector graphics for editing or publishing.',
    action: 'Download SVGs',
    icon: IconDownload,
  },
  {
    key: 'png',
    title: 'PNG',
    description:
      'Download the selected charts as standard image files, optimized for quick sharing and documents.',
    action: 'Download PNGs',
    icon: IconDownload,
  },
] as const;
