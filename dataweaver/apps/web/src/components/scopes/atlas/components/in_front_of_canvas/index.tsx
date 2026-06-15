import { Controls } from './controls';
import { ExportPanel } from './export_panel';
import { Selection } from './selection';
import { Tools } from './tools';

export const InFrontOfTheCanvas = () => {
  return (
    <>
      <Controls />
      <Tools />
      <ExportPanel />
      <Selection />
    </>
  );
};
