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

  return `${date.toLocaleString()} (${new Intl.RelativeTimeFormat("en", {
    numeric: "auto",
  }).format(
    Math.round((date.getTime() - Date.now()) / 60000),
    "minute",
  )})`;
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
