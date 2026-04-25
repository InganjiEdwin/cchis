type WithWardIdentity = {
  ward: number;
  ward_name: string;
};

export type WardGroup<T> = {
  wardId: number;
  wardName: string;
  items: T[];
};

export function groupByWardId<T extends WithWardIdentity>(items: T[]): Map<number, WardGroup<T>> {
  const groups = new Map<number, WardGroup<T>>();

  for (const item of items) {
    const existing = groups.get(item.ward);

    if (existing) {
      existing.items.push(item);
      continue;
    }

    groups.set(item.ward, {
      wardId: item.ward,
      wardName: item.ward_name,
      items: [item],
    });
  }

  return groups;
}
