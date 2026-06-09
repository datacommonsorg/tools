type Callback = () => void;

let isListening = false;
const CALLBACKS = new Set<Callback>();

const emitCallbacks = () => {
  for (const callback of CALLBACKS) callback();
};

export class Resize {
  #resized = false;

  constructor() {
    CALLBACKS.add(this.#onResize);
    this.#attachListenerIfFirst();
  }

  get resized(): boolean {
    return this.#resized;
  }

  readonly #onResize = (): void => {
    this.#resized = true;
  };

  readonly clear = (): void => {
    this.#resized = false;
  };

  readonly cleanup = (): void => {
    CALLBACKS.delete(this.#onResize);
    this.#detachListenerIfLast();
  };

  readonly #attachListenerIfFirst = (): void => {
    if (!isListening) {
      window.addEventListener('resize', emitCallbacks);
      isListening = true;
    }
  };

  readonly #detachListenerIfLast = (): void => {
    if (CALLBACKS.size === 0 && isListening) {
      window.removeEventListener('resize', emitCallbacks);
      isListening = false;
    }
  };
}
