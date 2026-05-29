import { useDataWeaverStore } from '~/store';
import s from './test.module.scss';

interface TestOutputProps {
  status: string;
}

export const TestOutput = ({ status }: TestOutputProps) => {
  const { cards } = useDataWeaverStore();
  return (
    <div className={s['test-output']}>
      <p>{status}</p>
      <pre>{JSON.stringify(cards, null, 2)}</pre>
    </div>
  );
};
