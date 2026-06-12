import 'react';

declare global {
  /**
   * Helper to make given props required within a union type.
   *
   * Use this when you have a union type and want to ensure that certain
   * properties are required for each member of the union, without affecting the
   * overall structure of the types.
   *
   * @example
   * ```ts
   * type A = { a: number; common?: string };
   * type B = { b: string; common?: string };
   * type Union = A | B;
   *
   * type Result = WithRequired<Union, 'common'>;
   * // Result is { a: number; common: string } | { b: string; common: string }
   * ```
   */
  type WithRequired<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

  /**
   * Utility type to distribute `Omit` across union types, ensuring that when T
   * is a union, the `Omit` is applied to each member of the union rather than
   * the union as a whole. This preserves the structure of each member type
   * while omitting the specified keys.
   *
   * Use this when you have a union type and want to omit certain properties
   * from each member of the union without losing the distinct types.
   *
   * @example
   * ```ts
   * type A = { a: number; common: string };
   * type B = { b: string; common: string };
   * type Union = A | B;
   *
   * type Result = DistributiveOmit<Union, 'common'>;
   * // Result is { a: number } | { b: string }
   * ```
   */
  type DistributiveOmit<T, K extends PropertyKey> = T extends unknown
    ? Omit<T, K>
    : never;
}

declare module 'react' {
  interface CSSProperties {
    [key: `--${string}`]: string | number | undefined;
  }
}
