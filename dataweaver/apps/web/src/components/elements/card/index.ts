import { CardBase } from './base';
import { CardChart } from './chart/chart';
import { CardText } from './text/text';

export const Card = {
  Base: CardBase,
  Text: CardText,
  Chart: CardChart,
} as const;
