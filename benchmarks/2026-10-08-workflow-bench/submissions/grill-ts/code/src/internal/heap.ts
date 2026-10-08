/** A binary min-heap ordered by `before(a, b)` ("a comes out before b"). */
export class Heap<T> {
  private readonly items: T[] = [];

  constructor(private readonly before: (a: T, b: T) => boolean) {}

  push(item: T): void {
    const items = this.items;
    items.push(item);
    let i = items.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (!this.before(items[i]!, items[parent]!)) break;
      [items[i], items[parent]] = [items[parent]!, items[i]!];
      i = parent;
    }
  }

  pop(): T | undefined {
    const items = this.items;
    const top = items[0];
    const last = items.pop();
    if (items.length === 0 || last === undefined) return top;
    items[0] = last;
    let i = 0;
    for (;;) {
      const left = 2 * i + 1;
      const right = left + 1;
      let best = i;
      if (left < items.length && this.before(items[left]!, items[best]!)) best = left;
      if (right < items.length && this.before(items[right]!, items[best]!)) best = right;
      if (best === i) return top;
      [items[i], items[best]] = [items[best]!, items[i]!];
      i = best;
    }
  }
}
