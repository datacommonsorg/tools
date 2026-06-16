'use client';

import { COLORS } from '@package/tokens/ts';
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
} from 'react';
import { createShapeId, type Editor, type TLShapeId, Tldraw } from 'tldraw';
import s from './atlas_provider.module.scss';
import {
  ATLAS_COMPONENTS,
  ATLAS_OVERLAYS,
  ATLAS_OVERRIDES,
  ATLAS_SHAPES,
  CARD_VARIANT_SIZE,
  ZOOM_STEPS,
} from './config';
import { ExportProvider } from './export_provider';
import { type AtlasContent, type CardVariant, contentToShape } from './helpers';
import { keepInView, placeCard } from './placement';
import { QueryProvider } from './query_provider';

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
interface CardHandle<TVariant extends CardVariant> {
  readonly id: TLShapeId;
  readonly variant: TVariant;
  update(props: Partial<Omit<ContentForVariant<TVariant>, 'variant'>>): void;
  remove(): void;
}

export interface AtlasContextProps {
  add<TVariant extends CardVariant>(
    content: ContentForVariant<TVariant>,
  ): CardHandle<TVariant>;
  getSelectedShapeIds(): string[];
}

const AtlasContext = createContext<AtlasContextProps | null>(null);

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
   * Resolves with the editor once `tldraw` mounts, so any editor actions work
   * before or after editor has been mounted via promise pattern.
   */
  const editorReadyRef = useRef(createDeferred<Editor>());

  /**
   * Track clones of cards that are created outside of the 'add' flow (copy /
   * paste, duplicate) so we can mirror updates and manage their lifecycle.
   */
  const clonesRef = useRef<Map<TLShapeId, Set<TLShapeId>>>(new Map());

  const mounted = useCallback((editor: Editor) => {
    // Render the dot grid (camera-tracked via the 'Grid' component slot)
    editor.updateInstanceState({ isGridMode: true });

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

    // Cards that appear outside of 'add' (copy/paste, duplicate) are clones:
    // Reposition them as they're created + mirror updates if loading
    const cleanupBeforeCreate = editor.sideEffects.registerBeforeCreateHandler(
      'shape',
      (shape) => {
        const originId = shape.meta.originId as TLShapeId | undefined;
        if (shape.type !== 'card' || originId === shape.id) return shape;

        const clonePosition = placeCard(
          editor,
          { w: shape.props.w, h: shape.props.h },

          // Use original shape as anchor point for clone
          { x: shape.x, y: shape.y },
        );

        // If original shape is still loading - clone its props and track
        // the clone so we can mirror updates to it as they arrive
        const originShape =
          shape.props.isLoading && originId
            ? editor.getShape(originId)
            : undefined;
        if (originShape && originShape.type === 'card') {
          const clones =
            clonesRef.current.get(originShape.id) ?? new Set<TLShapeId>();
          clones.add(shape.id);
          clonesRef.current.set(originShape.id, clones);

          return {
            ...shape,
            ...clonePosition,
            props: { ...originShape.props },
          };
        }

        // For all other clones - just reposition them and return as is
        return { ...shape, ...clonePosition };
      },
    );

    // Whenever a card is placed (new or clone), pan the camera so it stays in
    // view if it landed off-screen
    const cleanupAfterCreate = editor.sideEffects.registerAfterCreateHandler(
      'shape',
      (shape) => {
        if (shape.type !== 'card') return;

        keepInView(editor, {
          x: shape.x,
          y: shape.y,
          w: shape.props.w,
          h: shape.props.h,
        });
      },
    );

    // If a still-loading shape is deleted - delete its clones too (they'll
    // never resolve into real content)
    const cleanupAfterDelete = editor.sideEffects.registerAfterDeleteHandler(
      'shape',
      (shape) => {
        if (shape.type !== 'card') return;

        const clones = clonesRef.current.get(shape.id);
        if (!clones) return;

        for (const cloneId of clones) {
          if (editor.getShape(cloneId)) editor.deleteShapes([cloneId]);
        }

        clonesRef.current.delete(shape.id);
      },
    );

    // Release any canvas writes that were issued before mount
    editorReadyRef.current.resolve(editor);

    // Let the CSS know we're mounted so it can fade the canvas in
    editor.getContainer().dataset.isMounted = 'true';

    return () => {
      cleanupBeforeCreate();
      cleanupAfterCreate();
      cleanupAfterDelete();

      // Swap in a fresh deferred and drop clone tracking tied to this
      // editor, so any future remount starts clean rather than chaining
      // writes onto the editor we just tore down
      editorReadyRef.current = createDeferred<Editor>();
      clonesRef.current.clear();
    };
  }, []);

  const providerValue = useMemo<AtlasContextProps>(
    () => ({
      getSelectedShapeIds: () =>
        editorRef.current?.getSelectedShapeIds().map(String) ?? [],
      add: (content) => {
        const shapeId = createShapeId();

        // First: Create the shape with any immediately available content, once
        // the editor has mounted (immediately, if it already has)
        editorReadyRef.current.promise.then((editor) => {
          const position = placeCard(
            editor,
            CARD_VARIANT_SIZE[content.variant],
          );
          editor.createShape({
            ...contentToShape(shapeId, content, position),

            // Stamp the origin ID so clones (copy/paste) can trace back to the
            // card they came from and mirror its streamed updates
            meta: { originId: shapeId },
          });
        });

        return {
          id: shapeId,
          variant: content.variant,
          update(props) {
            editorReadyRef.current.promise.then((editor) => {
              // The shape may have been deleted before an async update resolves
              if (!editor.getShape(shapeId)) return;

              // Update the card with the new content
              editor.updateShape({ id: shapeId, type: 'card', props });

              // If this card has clones, mirror the update to them too
              const clones = clonesRef.current.get(shapeId);
              if (!clones) return;

              for (const cloneId of clones) {
                if (editor.getShape(cloneId)) {
                  editor.updateShape({ id: cloneId, type: 'card', props });
                }
              }

              // Once resolved, no further updates arrive so stop following
              if (props.isLoading === false) {
                clonesRef.current.delete(shapeId);
              }
            });
          },
          remove() {
            editorReadyRef.current.promise.then((editor) =>
              editor.deleteShapes([shapeId]),
            );
          },
        };
      },
    }),
    [],
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
