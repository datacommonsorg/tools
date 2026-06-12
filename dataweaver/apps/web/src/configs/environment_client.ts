export const IS_BROWSER = typeof window !== 'undefined';

export const IS_APPLE =
  typeof navigator !== 'undefined' &&
  /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
