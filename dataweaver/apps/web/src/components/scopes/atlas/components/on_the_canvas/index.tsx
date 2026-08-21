import { Portal } from '~/components/primitives/portal';
import s from './index.module.scss';
import { Selection } from './selection/selection';

export const OnTheCanvas = () => {
  return (
    <Portal className={s.container}>
      <Selection />
    </Portal>
  );
};
