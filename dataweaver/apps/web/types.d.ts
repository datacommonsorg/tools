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
  type WithRequired<T, K extends keyof T> = T extends unknown
    ? Omit<T, K> & Required<Pick<T, K>>
    : never;
}

declare module 'react' {
  interface CSSProperties {
    [key: `--${string}`]: string | number | undefined;
  }
}
