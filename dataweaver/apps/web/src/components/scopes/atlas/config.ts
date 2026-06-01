import type { TLComponents } from 'tldraw';
import { Grid } from './components/grid';
import { CardChartShapeUtil } from './shapes/card_chart';
import { CardTextShapeUtil } from './shapes/card_text';

export const ATLAS_COMPONENTS = { Grid } as const satisfies TLComponents;

export const ATLAS_SHAPES = [CardTextShapeUtil, CardChartShapeUtil] as const;
