export function isSentinel2(productType: string): boolean {
  return productType.startsWith("SENTINEL_2");
}

export function isSentinel3(productType: string): boolean {
  return productType.startsWith("SENTINEL_3");
}

export function getMission(productType: string): string {
  if (isSentinel3(productType)) return "Sentinel-3";
  if (isSentinel2(productType)) return "Sentinel-2";
  return "Sentinel-1";
}

export function getInstrument(productType: string): string {
  if (isSentinel3(productType)) return "SLSTR";
  if (isSentinel2(productType)) return "MSI";
  return "SAR";
}
