import type { ScanMetadata } from "./types";

export function patientGroups(scans: ScanMetadata[]) {
  const groups = new Map<string, ScanMetadata[]>();
  for (const scan of scans) groups.set(scan.patient_id, [...(groups.get(scan.patient_id) || []), scan]);
  return [...groups].map(([patientId, records]) => {
    const history = records.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.scan_id.localeCompare(a.scan_id));
    return {patientId, latest: history[0], history};
  }).sort((a, b) => Date.parse(b.latest.created_at) - Date.parse(a.latest.created_at));
}
