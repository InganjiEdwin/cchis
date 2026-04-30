export function getLatestTimestamp(timestamps: Array<string | null | undefined>) {
  return timestamps.reduce<string | null>((latest, timestamp) => {
    if (!timestamp) {
      return latest;
    }

    if (!latest || new Date(timestamp).getTime() > new Date(latest).getTime()) {
      return timestamp;
    }

    return latest;
  }, null);
}

export function formatRelativeTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return "No timestamp available";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const diffMs = date.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60000);
  const absMinutes = Math.abs(diffMinutes);

  if (absMinutes < 1) {
    return "Just now";
  }

  if (absMinutes < 60) {
    return `${Math.abs(diffMinutes)}m ago`;
  }

  const diffHours = Math.round(diffMinutes / 60);
  const absHours = Math.abs(diffHours);

  if (absHours < 24) {
    return `${Math.abs(diffHours)}h ago`;
  }

  const diffDays = Math.round(diffHours / 24);
  return `${Math.abs(diffDays)}d ago`;
}

export function describeFreshness(timestamp: string | null, thresholdMinutes: number) {
  if (!timestamp) {
    return {
      label: "No current data timestamp",
      isStale: true,
    };
  }

  const ageMs = Date.now() - new Date(timestamp).getTime();

  if (ageMs > thresholdMinutes * 60 * 1000) {
    return {
      label: "Data may be stale",
      isStale: true,
    };
  }

  return {
    label: "Data is within the current freshness window",
    isStale: false,
  };
}
