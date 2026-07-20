import { type ChangeEvent, useRef } from 'react';
import { Button } from '~/components/elements/button';
import { Menu as MenuElement } from '~/components/elements/menu';
import { toast } from '~/components/foundations/toaster/store';
import { IconClose } from '~/components/primitives/icons/close';
import { IconImport } from '~/components/primitives/icons/import';
import {
  ImportError,
  importState,
  STATE_VERSION,
} from '~/store/serialization';
import s from './menu.module.scss';

interface MenuProps {
  id: string;
  onClose(): void;
}

export const Menu = ({ id, onClose }: MenuProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const importFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    const file = files === null ? undefined : files[0];

    // Reset so the same file can be re-imported
    event.target.value = '';

    if (!file) {
      toast('Import failed', 'No file was selected for import.');
      return;
    }

    try {
      await importState(file);
      onClose();
    } catch (error) {
      if (error instanceof ImportError && error.reason === 'version-mismatch') {
        const found =
          error.fileVersion === undefined
            ? 'an unknown version'
            : `version ${error.fileVersion}`;

        toast(
          'Import failed',
          `This file was exported from ${found}. The canvas expects version ${STATE_VERSION}.`,
        );
        return;
      }

      toast('Import failed', 'The selected file is not a valid canvas export.');
    }
  };

  return (
    <MenuElement
      id={id}
      className={s.menu}
      aria-label="Import canvas"
      onClose={onClose}
      // Keep canvas gestures from leaking through to tldraw behind the menu
      onPointerDown={(event) => event.stopPropagation()}
      onWheelCapture={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <header className={s['header-container']}>
        <h2 className={s.title}>Import canvas</h2>

        <Button
          icon={IconClose}
          className={s['button-close']}
          size="large"
          variant="flat"
          tone="subtle"
          aria-label="Close import"
          onClick={onClose}
        />
      </header>

      <div className={s['content-container']}>
        <p className={s.description}>
          Upload a previously exported workspace to populate the canvas and
          resume the exploration.
        </p>

        <button
          type="button"
          className={s['button-browse']}
          onClick={() => {
            const fileInput = fileInputRef.current;
            if (fileInput) fileInput.click();
          }}
        >
          <IconImport className={s['icon-import']} />
          <span className={s['browse-label']}>Browse file</span>
          <span className={s['browse-format']}>JSON format</span>
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept=".json,application/json"
          hidden
          onChange={importFile}
        />
      </div>
    </MenuElement>
  );
};
