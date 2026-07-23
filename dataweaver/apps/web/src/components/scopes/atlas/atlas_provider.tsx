'use client';

import { COLORS } from '@package/tokens/ts';
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createShapeId, type Editor, type TLShapeId, Tldraw } from 'tldraw';
import s from './atlas_provider.module.scss';
import {
  ATLAS_COMPONENTS,
  ATLAS_OVERLAYS,
  ATLAS_OVERRIDES,
  ATLAS_SHAPES,
  CARD_VARIANT_SIZE_DEFAULT,
  ZOOM_STEPS,
} from './config';
import { ExportProvider } from './export_provider';
import { type AtlasContent, type CardVariant, contentToShape } from './helpers';
import { QueryProvider } from './query_provider';
import { registerCardBringToFront } from './register_card_bring_to_front';
import { type CardClones, registerCardClones } from './register_card_clones';
import {
  type CardPlacement,
  fitCardSize,
  registerCardPlacement,
} from './register_card_placement';
import { registerCardStoreSync } from './register_card_store_sync';
import { registerCardTabNavigation } from './register_card_tab_navigation';

/** The content shape that corresponds to a given card variant. */
type ContentForVariant<TVariant extends CardVariant> = Extract<
  AtlasContent,
  { variant: TVariant }
>;

/**
 * Handle returned by `atlas.add(...)`. Use it to populate a card with real
 * data as it arrives, or to remove the card from the canvas. The handle is
 * typed against the variant passed to `add`, so updates can only set fields
 * that belong to that variant.
 */
export interface CardHandle<TVariant extends CardVariant> {
  readonly id: TLShapeId;
  readonly variant: TVariant;
  update(props: Partial<Omit<ContentForVariant<TVariant>, 'variant'>>): void;
  remove(): void;
}

export interface AtlasContextProps {
  /** The mounted tldraw editor, or `null` before mount. */
  editor: Editor | null;
  add<TVariant extends CardVariant>(
    content: ContentForVariant<TVariant>,
    customId?: string,
  ): CardHandle<TVariant>;
}

const AtlasContext = createContext<AtlasContextProps | null>(null);

/** The mounted tldraw editor together with its registered card systems. */
interface AtlasCanvas {
  editor: Editor;
  placeCard: CardPlacement['place'];
  cloneMirrorUpdate: CardClones['mirrorUpdate'];
}

/** A promise paired with its resolver, so it can be settled imperatively. */
interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

const createDeferred = <T,>(): Deferred<T> => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((response) => (resolve = response));
  return { promise, resolve };
};

interface AtlasProviderProps {
  children: ReactNode;
  licenseKey?: string;
}

export const AtlasProvider = ({ children, licenseKey }: AtlasProviderProps) => {
  /**
   * Use this for reads that must return a value now; use `canvasReadyRef` for
   * writes that can wait for mount.
   */
  const [editor, setEditor] = useState<Editor | null>(null);

  /**
   * Resolves with the editor and its placement system once `tldraw` mounts,
   * so any canvas actions work before or after mount via promise pattern.
   */
  const canvasReadyRef = useRef(createDeferred<AtlasCanvas>());

  const mounted = useCallback((editor: Editor) => {
    // Define camera zoom levels
    editor.setCameraOptions({ zoomSteps: [...ZOOM_STEPS] });

    // Style built-in theme to match our design system
    editor.updateThemes((themes) => {
      themes.default.fonts.draw.fontFamily = '"Google Sans", sans-serif';
      themes.default.fontSize = 24;
      themes.default.lineHeight = 1.25;
      themes.default.colors.light.black.solid = `rgb(${COLORS['atlas-content']})`;
      themes.default.colors.light.selectionStroke = `rgb(${COLORS['atlas-accent']})`;
      return themes;
    });

    // Register our custom card placement, clone tracking, store syncing and tab
    // navigation systems respectively
    const placement = registerCardPlacement(editor);
    const clones = registerCardClones(editor);
    const cleanupStoreSync = registerCardStoreSync(editor);
    const cleanupTabNavigation = registerCardTabNavigation(editor);
    const cleanupBringToFront = registerCardBringToFront(editor);

    // Expose the editor for synchronous reads and release any canvas writes
    // that were issued before mount
    setEditor(editor);
    canvasReadyRef.current.resolve({
      editor,
      placeCard: placement.place,
      cloneMirrorUpdate: clones.mirrorUpdate,
    });

    // Let the CSS know we're mounted so it can fade the canvas in
    editor.getContainer().dataset.isMounted = 'true';

    return () => {
      placement.cleanup();
      clones.cleanup();
      cleanupStoreSync();
      cleanupTabNavigation();
      cleanupBringToFront();

      // Swap in a fresh deferred tied to this editor, so any future remount
      // starts clean rather than chaining writes onto the editor we just
      // tore down
      setEditor(null);
      canvasReadyRef.current = createDeferred<AtlasCanvas>();
    };
  }, []);

  const providerValue = useMemo<AtlasContextProps>(
    () => ({
      editor,
      add: (content, customId) => {
        const shapeId = customId ? createShapeId(customId) : createShapeId();

        // First: Create the shape with any immediately available content, once
        // the editor has mounted (immediately, if it already has)
        canvasReadyRef.current.promise.then(({ editor, placeCard }) => {
          // Cap the default footprint to the grid's column width so the
          // breakpoint's card count actually fits side by side (and cards
          // stack on narrow mobile screens)
          const size = fitCardSize(
            editor,
            CARD_VARIANT_SIZE_DEFAULT[content.variant],
          );
          const position = placeCard(shapeId, size);
          editor.createShape({
            ...contentToShape(shapeId, content, position, size),

            // Stamp the origin ID so clones (copy/paste) can trace back to the
            // card they came from and mirror its streamed updates
            meta: { originId: shapeId },
          });
        });

        return {
          id: shapeId,
          variant: content.variant,
          update(props) {
            canvasReadyRef.current.promise.then(
              ({ editor, cloneMirrorUpdate }) => {
                // The shape may have been deleted before an async update resolves
                if (!editor.getShape(shapeId)) return;

                // Update the card with the new content, and mirror it to any
                // clones still following this card
                editor.updateShape({ id: shapeId, type: 'card', props });
                cloneMirrorUpdate(shapeId, props);
              },
            );
          },
          remove() {
            canvasReadyRef.current.promise.then(({ editor }) =>
              editor.deleteShapes([shapeId]),
            );
          },
        };
      },
    }),
    [editor],
  );

  return (
    <AtlasContext.Provider value={providerValue}>
      <QueryProvider>
        <ExportProvider>
          <Tldraw
            className={s.tldraw}
            hideUi
            components={ATLAS_COMPONENTS}
            overrides={ATLAS_OVERRIDES}
            shapeUtils={ATLAS_SHAPES}
            overlayUtils={ATLAS_OVERLAYS}
            onMount={mounted}
            licenseKey={licenseKey}
          />
          {children}
        </ExportProvider>
      </QueryProvider>
    </AtlasContext.Provider>
  );
};

/** Read the atlas — must be used inside `<AtlasProvider>`. */
export const useAtlas = (): AtlasContextProps => {
  const context = useContext(AtlasContext);
  if (!context) {
    throw new Error("'useAtlas' must be used within 'AtlasProvider'.");
  }

  return context;
};
