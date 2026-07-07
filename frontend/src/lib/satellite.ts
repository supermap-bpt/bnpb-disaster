export function isSentinel2(productType: string): boolean {
  return productType.startsWith("SENTINEL_2");
}

export function getMission(productType: string): string {
  return isSentinel2(productType) ? "Sentinel-2" : "Sentinel-1";
}

export function getInstrument(productType: string): string {
  return isSentinel2(productType) ? "MSI" : "SAR";
}
