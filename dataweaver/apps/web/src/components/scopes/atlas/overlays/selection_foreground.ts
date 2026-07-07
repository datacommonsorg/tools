import { SelectionForegroundOverlayUtil } from 'tldraw';

/**
 * When more than one shape is selected we render our own selection UI (see the
 * `Selection` component in the `InFrontOfTheCanvas` slot), so suppress tldraw's
 * default selection foreground — its border plus resize and rotate handles — in
 * that case. This is also what blocks rotation of a multi-selection: with no
 * rotate handle there's no way to start a rotation.
 *
 * For a single card we keep the overlay *active* — the inherited
 * `getOverlays`/`getGeometry`/`getCursor` still hit-test the card's edges and
 * corners, which is what swaps the cursor to the resize arrows and lets a drag
 * start a resize — but `render` is a no-op, so none of that selection UI (frame
 * or handles) is ever drawn. The card's own CSS handles the selected look.
 */
export class AtlasSelectionForegroundOverlayUtil extends SelectionForegroundOverlayUtil {
  override isActive() {
    if (this.editor.getSelectedShapeIds().length > 1) return false;
    return super.isActive();
  }

  override render() {
    // Intentionally draw nothing: resize is cursor-only, with no visible
    // handles or selection frame. Hit-testing/cursors come from the inherited
    // overlay geometry, which is unaffected by skipping the visuals here
  }
}
