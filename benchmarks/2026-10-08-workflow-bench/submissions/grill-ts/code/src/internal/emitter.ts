type Listener = (...args: never[]) => void;

/**
 * Synchronous event emitter. Each registration is independent, an emit iterates a snapshot taken
 * when it begins, and listener exceptions are swallowed so user code can't corrupt the caller.
 */
export class Emitter<Events extends { [K in keyof Events]: Listener }> {
  private readonly listeners = new Map<keyof Events, { fn: Listener }[]>();

  constructor(names: readonly (keyof Events)[]) {
    for (const name of names) this.listeners.set(name, []);
  }

  on<E extends keyof Events>(event: E, fn: Events[E]): () => void {
    const list = this.listeners.get(event);
    if (!list) throw new Error(`unknown event: ${String(event)}`);
    const registration = { fn };
    list.push(registration);
    return () => {
      const i = list.indexOf(registration);
      if (i !== -1) list.splice(i, 1);
    };
  }

  emit<E extends keyof Events>(event: E, ...args: Parameters<Events[E]>): void {
    for (const { fn } of [...this.listeners.get(event)!]) {
      try {
        (fn as (...a: Parameters<Events[E]>) => void)(...args);
      } catch {
        // Listener errors are deliberately ignored (see NOTES.md).
      }
    }
  }
}
