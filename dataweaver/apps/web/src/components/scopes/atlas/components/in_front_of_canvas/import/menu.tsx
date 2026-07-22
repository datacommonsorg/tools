import { type ChangeEvent, type DragEvent, useRef, useState } from 'react';
import { Button } from '~/components/elements/button';
import { Menu as MenuElement } from '~/components/elements/menu';
import { toast } from '~/components/foundations/toaster/store';
import { IconClose } from '~/components/primitives/icons/close';
import { IconImport } from '~/components/primitives/icons/import';
import { ImportError, importState } from '~/store/serialization';
import s from './menu.module.scss';

interface MenuProps {
  id: string;
  onClose(): void;
}

export const Menu = ({ id, onClose }: MenuProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [isDraggingOver, setIsDraggingOver] = useState(false);

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    const file = files === null ? undefined : files[0];
    event.target.value = '';
    importFile(file);
  };

  const dropFile = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDraggingOver(false);
    importFile(event.dataTransfer.files[0]);
  };

  const importFile = async (file: File | undefined) => {
    if (!file) {
      toast('Import failed', 'No file was selected for import.');
      return;
    }

    try {
      await importState(file);
      onClose();
    } catch (error) {
      toast(
        'Import failed',
        error instanceof ImportError
          ? error.message
          : 'An unexpected error occurred during import.',
      );
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
          data-is-dragging-over={isDraggingOver}
          onClick={() => {
            const fileInput = fileInputRef.current;
            if (fileInput) fileInput.click();
          }}
          // Here we 'preventDefault' to prevent browser opening early
          onDragOver={(event) => {
            event.preventDefault();
            setIsDraggingOver(true);
          }}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDraggingOver(true);
          }}
          onDragLeave={() => setIsDraggingOver(false)}
          onDrop={dropFile}
        >
          <IconImport className={s['icon-import']} />
          <span className={s['browse-label']}>
            {isDraggingOver ? 'Drop to import' : 'Browse or drop file'}
          </span>
          <span className={s['browse-format']}>JSON format</span>
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept=".json,application/json"
          hidden
          onChange={selectFile}
        />
      </div>
    </MenuElement>
  );
};
