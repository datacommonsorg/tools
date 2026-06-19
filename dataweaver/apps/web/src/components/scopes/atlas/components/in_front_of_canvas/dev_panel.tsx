'use client';

import { useRef } from 'react';
import { Button } from '~/components/elements/button';
import { useDevMode } from '~/hooks/use_dev_mode';
import { exportState, importState } from '~/store/serialization';
import s from './dev_panel.module.scss';

const BUTTON_COLOR_SCHEME = {
  base: 'var(--color-control-surface)',
  'base-hover': 'var(--color-control-surface-hover)',
  content: 'var(--color-control-accent)',
  'content-hover': 'var(--color-control-accent)',
};

export const DevPanel = () => {
  const isDev = useDevMode();
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isDev) return null;

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      await importState(file);
    } catch (err) {
      console.error('[DevPanel] Import failed:', err);
    }

    // Reset so the same file can be re-imported.
    e.target.value = '';
  };

  return (
    <div className={s.container}>
      <Button
        size="small"
        colorScheme={BUTTON_COLOR_SCHEME}
        onClick={exportState}
      >
        Export State
      </Button>
      <Button
        size="small"
        colorScheme={BUTTON_COLOR_SCHEME}
        onClick={() => fileInputRef.current?.click()}
      >
        Import State
      </Button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        hidden
        onChange={handleImport}
      />
    </div>
  );
};
