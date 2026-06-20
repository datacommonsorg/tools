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
      'Your JSON code will appear here once you add content to your canvas.',
    action: 'Generate API Code',
    icon: IconCopy,
  },
  {
    key: 'csv',
    title: 'CSV',
    description:
      "You'll get a separate file for every card that contains data.",
    action: 'Download CSVs',
    icon: IconDownload,
  },
  {
    key: 'ai-narrative',
    title: 'AI Narrative',
    description: 'Gemini will summarize your canvas into a narrative.',
    action: 'Generate narrative',
    icon: IconNarrative,
  },
  {
    key: 'ai-infographic',
    title: 'AI Infographic',
    description: 'Gemini can generate a visual infographic from your canvas.',
    action: 'Generate with Gemini',
    icon: IconShapes,
  },
  {
    key: 'svg',
    title: 'SVG',
    description:
      "You'll receive a separated vector svg file for each of your selected cards.",
    action: 'Download SVGs',
    icon: IconDownload,
  },
  {
    key: 'png',
    title: 'PNG',
    description:
      "You'll receive a separated raster png file for each of your selected cards.",
    action: 'Download PNGs',
    icon: IconDownload,
  },
] as const;
