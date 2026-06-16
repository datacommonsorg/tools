import { CardBase } from './base';
import { CardChart } from './chart/chart';
import { CardTable } from './table/table';
import { CardText } from './text';

export const Card = {
  Base: CardBase,
  Text: CardText,
  Chart: CardChart,
  Table: CardTable,
} as const;
