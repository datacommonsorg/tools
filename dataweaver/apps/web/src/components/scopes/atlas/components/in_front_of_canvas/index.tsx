import { Controls } from './controls';
import { ExportPanel } from './export/export_panel';
import { Tools } from './tools';

export const InFrontOfTheCanvas = () => {
  return (
    <>
      <Controls />
      <Tools />
      <ExportPanel />
    </>
  );
};
