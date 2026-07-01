import { CardBase } from './base';
import { CardChart } from './chart/chart';
import { CardFooter } from './footer';
import { CardText } from './text';

export const Card = {
  Base: CardBase,
  Text: CardText,
  Chart: CardChart,
  Footer: CardFooter,
} as const;
