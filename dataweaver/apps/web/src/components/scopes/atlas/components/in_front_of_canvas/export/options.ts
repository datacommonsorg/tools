import { IconCopy } from '~/components/primitives/icons/copy';
import { IconDownload } from '~/components/primitives/icons/download';
import { IconExport } from '~/components/primitives/icons/export';
import { IconNarrative } from '~/components/primitives/icons/narrative';
import { IconShapes } from '~/components/primitives/icons/shapes';

/** The available export formats. */
// TODO: Implement the actual export functionality for each of these formats
export const EXPORT_OPTIONS = [
  {
    key: 'api-request-code',
    title: 'API request code',
    description: 'Get the REST V2 API code to query data from selected cards.',
    action: 'Generate API code',
    icon: IconCopy,
  },
  {
    key: 'csv',
    title: 'CSV',
    description: 'Download raw data from selected cards as a CSV spreadsheet.',
    action: 'Download CSVs',
    icon: IconDownload,
  },
  {
    key: 'ai-narrative',
    title: 'AI narrative',
    description:
      'Generate a text-based analytical summary from selected cards.',
    action: 'Generate narrative',
    icon: IconNarrative,
  },
  {
    key: 'ai-infographic',
    title: 'AI infographic',
    description:
      'Transform data from selected cards into a visual presentation.',
    action: 'Generate with Gemini',
    icon: IconShapes,
  },
  {
    key: 'svg',
    title: 'SVG',
    description:
      'Export selected charts as vector graphics for editing or publishing.',
    action: 'Download SVGs',
    icon: IconDownload,
  },
  {
    key: 'png',
    title: 'PNG',
    description: 'Download selected charts as image files for quick sharing.',
    action: 'Download PNGs',
    icon: IconDownload,
  },
] as const;

/**
 * Full-workspace export — unlike the per-card formats above it doesn't need a
 * selection, so it's offered whenever the canvas has content. Its download
 * pairs with the import menu, which restores the workspace from the file.
 */
export const EXPORT_OPTION_CANVAS = {
  key: 'canvas',
  title: 'Export full canvas',
  description:
    'Export the full workspace to restore and resume exploration on the canvas later.',
  action: 'Export canvas',
  icon: IconExport,
} as const;
