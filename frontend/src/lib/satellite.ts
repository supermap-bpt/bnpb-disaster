export function isSentinel2(productType: string): boolean {
  return productType.startsWith("SENTINEL_2");
}

export function isSentinel3(productType: string): boolean {
  return productType.startsWith("SENTINEL_3");
}

export function isDemnas(productType: string): boolean {
  return productType.startsWith("DEMNAS");
}

export function getDemnasPreviewImageUrl(id: string): string {
  return `https://tanahair.indonesia.go.id/demnas/images/DEMNAS_${id}.jpg`;
}

// Assumed universal (no per-tile version variation observed) - see the
// design spec's "Open Assumption" note. Shared so the popup's displayed
// filename can never drift from the actual download link's filename param.
export function getDemnasFilename(id: string): string {
  return `DEMNAS_${id}_v1.0.tif`;
}

export function getDemnasLoginDownloadUrl(id: string): string {
  return `https://tanahair.indonesia.go.id/portal-web/login?page=/unduh/demnas&filename=${encodeURIComponent(getDemnasFilename(id))}`;
}

export function getMission(productType: string): string {
  if (isDemnas(productType)) return "DEMNAS";
  if (isSentinel3(productType)) return "Sentinel-3";
  if (isSentinel2(productType)) return "Sentinel-2";
  return "Sentinel-1";
}

export function getInstrument(productType: string): string {
  if (isDemnas(productType)) return "DEM";
  if (isSentinel3(productType)) return "SLSTR";
  if (isSentinel2(productType)) return "MSI";
  return "SAR";
}

// Which product types have a real, renderable preview image. Shared by
// ProductCard's thumbnail and MapView's "View on Map" preview fetch, so both
// stay in sync about which types even have an image worth requesting.
const THUMBNAIL_SUPPORTED: Record<string, boolean> = {
  SENTINEL_1_GRD: true,
  SENTINEL_1_SLC: false,
  SENTINEL_2_L2A: true,
  SENTINEL_2_L1C: false,
  SENTINEL_3_SLSTR_L2_LST: true,
  SENTINEL_3_SLSTR_L2_WST: false,
  DEMNAS_25K: false,
  DEMNAS_50K: false,
};

export function hasPreview(productType: string): boolean {
  return THUMBNAIL_SUPPORTED[productType] ?? false;
}
