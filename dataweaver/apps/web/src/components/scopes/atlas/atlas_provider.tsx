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
import { ExportProvider } from './components/in_front_of_canvas/export/export_provider';
import {
  ATLAS_COMPONENTS,
  ATLAS_OVERLAYS,
  ATLAS_OVERRIDES,
  ATLAS_SHAPES,
  ZOOM_STEPS,
} from './config';
import {
  type AtlasContent,
  type CardVariant,
  contentToShape,
  gridPosition,
} from './helpers';

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

interface AtlasContextProps {
  add<TVariant extends CardVariant>(
    content: ContentForVariant<TVariant>,
  ): CardHandle<TVariant>;
}

const AtlasContext = createContext<AtlasContextProps | null>(null);

type EditorOperation = (editor: Editor) => void;

interface AtlasProviderProps {
  children: ReactNode;
  licenseKey?: string;
}

export const AtlasProvider = ({ children, licenseKey }: AtlasProviderProps) => {
  const editorRef = useRef<Editor | null>(null);
  const pendingShapesQueueRef = useRef<EditorOperation[]>([]);

  // TODO: For now using count for positioning - we likely want to use a smarter
  // approach that accounts for deleted content and doesn't rely on order of
  // addition, etc later once we hook up to real data
  const countRef = useRef(0);

  const withEditor = useCallback((operation: EditorOperation) => {
    const editor = editorRef.current;

    // If we have the editor available - perform the operation immediately
    if (editor) operation(editor);
    // Otherwise queue it up for when the editor is ready (e.g. once mounted)
    else pendingShapesQueueRef.current.push(operation);
  }, []);

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
      themes.default.colors.light.black.solid = `rgb(${COLORS['surface-content']})`;
      themes.default.colors.light.selectionStroke = `rgb(${COLORS['control-accent']})`;
      return themes;
    });

    editorRef.current = editor;
    countRef.current = 0;

    // If there were any operations queued up before the editor was ready,
    // run them now that we've mounted
    const queued = pendingShapesQueueRef.current;
    pendingShapesQueueRef.current = [];
    for (const operation of queued) operation(editor);
  }, []);

  const providerValue = useMemo<AtlasContextProps>(
    () => ({
      add: (content) => {
        const shapeId = createShapeId();

        // First: Create the shape with any immediately available content
        withEditor((editor) => {
          editor.createShape(
            contentToShape(shapeId, content, gridPosition(countRef.current)),
          );

          // Increment count for next shape's position
          countRef.current++;
        });

        // Then: Return handle that allows for future updates to the shape as more
        // content becomes available, or for the shape to be removed
        return {
          id: shapeId,
          variant: content.variant,
          update(props) {
            withEditor((editor) => {
              // The shape may have been deleted before an async update resolves
              if (!editor.getShape(shapeId)) return;

              editor.updateShape({ id: shapeId, type: 'card', props });
            });
          },
          remove() {
            withEditor((editor) => editor.deleteShapes([shapeId]));
          },
        };
      },
    }),
    [withEditor],
  );

  return (
    <AtlasContext.Provider value={providerValue}>
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
