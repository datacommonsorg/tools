/**
 * Linearly remap `value` from the input range `[inMin, inMax]` onto the output
 * range `[outMin, outMax]`. Not clamped — values outside the input range map
 * proportionally outside the output range.
 *
 * @example
 * mapRange(100, 0, 800, 0, 200); // 25
 */
export const mapRange = (
  value: number,
  inMin: number,
  inMax: number,
  outMin: number,
  outMax: number,
) => outMin + ((value - inMin) / (inMax - inMin)) * (outMax - outMin);
