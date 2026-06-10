import { SelectionForegroundOverlayUtil } from 'tldraw';

/**
 * When more than one shape is selected we render our own selection UI (see the
 * `Selection` component in the `InFrontOfTheCanvas` slot), so suppress tldraw's
 * default selection foreground — its border plus resize and rotate handles — in
 * that case. This is also what blocks rotation of a multi-selection: with no
 * rotate handle there's no way to start a rotation.
 *
 * Single-shape selection keeps the default behavior; the card shape util
 * already renders nothing for (`hideSelectionBoundsFg` / `hideRotateHandle`).
 */
export class AtlasSelectionForegroundOverlayUtil extends SelectionForegroundOverlayUtil {
  override isActive() {
    if (this.editor.getSelectedShapeIds().length > 1) return false;
    return super.isActive();
  }
}
