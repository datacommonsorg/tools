import { CardBase } from './base';
import { CardChart } from './chart/chart';
import { CardContent } from './content';
import { CardFooter } from './footer';
import { CardText } from './text';

export const Card = {
  Base: CardBase,
  Text: CardText,
  Chart: CardChart,
  Footer: CardFooter,
  Content: CardContent,
} as const;
