import type { FilterFormValues } from "../schemas/filterSchema";
import type { AoiRing, Footprint, GeocodeResult, PreviewData, SearchResultItem } from "../context/GISContext";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail ?? `Request failed with status ${response.status}`);
  }
  return body as T;
}

export async function fetchGeocodeSuggestions(query: string): Promise<GeocodeResult[]> {
  const url = `${API_BASE_URL}/api/geocode?q=${encodeURIComponent(query)}`;
  const response = await fetch(url);
  const data = await parseJsonOrThrow<{ results: GeocodeResult[] }>(response);
  return data.results;
}

export interface SearchResult {
  results: SearchResultItem[];
  total: number;
}

export async function fetchSearch(
  filter: FilterFormValues,
  aoiRing: AoiRing,
  skip = 0
): Promise<SearchResult> {
  const params = new URLSearchParams();
  for (const productType of filter.productType) {
    params.append("productType", productType);
  }
  params.set("dateFrom", filter.dateFrom);
  params.set("dateUntil", filter.dateUntil);
  params.set("cloudCoverMax", String(filter.cloudCoverMax));
  params.set("aoi", aoiRing.flat().join(","));
  params.set("skip", String(skip));
  const url = `${API_BASE_URL}/api/search?${params.toString()}`;
  const response = await fetch(url);
  return parseJsonOrThrow<SearchResult>(response);
}

export async function fetchPreview(productId: string): Promise<PreviewData> {
  const url = `${API_BASE_URL}/api/preview/${encodeURIComponent(productId)}`;
  const response = await fetch(url);
  const data = await parseJsonOrThrow<PreviewData>(response);
  // Backend returns tileUrl as a relative path ("/api/preview-image/...") -
  // make it absolute so <ImageOverlay>/<img> can fetch it directly.
  return { ...data, tileUrl: `${API_BASE_URL}${data.tileUrl}` };
}

export function getDownloadUrl(productId: string): string {
  return `${API_BASE_URL}/api/download/${encodeURIComponent(productId)}`;
}

export function getPreviewImageUrl(productId: string): string {
  return `${API_BASE_URL}/api/preview-image/${encodeURIComponent(productId)}`;
}

export interface ProductAttribute {
  name: string;
  value: string;
}

export async function fetchProductAttributes(productId: string): Promise<ProductAttribute[]> {
  const url = `${API_BASE_URL}/api/products/${encodeURIComponent(productId)}/attributes`;
  const response = await fetch(url);
  const data = await parseJsonOrThrow<{ attributes: ProductAttribute[] }>(response);
  return data.attributes;
}

export interface AttributeRow {
  label: string;
  value: string;
}

export interface SelectedProductPayload {
  id: string;
  name: string;
  mission: string;
  instrumentName: string;
  polarisation: string;
  sensingTime: string;
  size: string;
  footprint: SearchResultItem["footprint"];
  attributes: ProductAttribute[];
}

export interface SaveSatelliteResponse {
  success: boolean;
  message: string;
  satelliteId: string | null;
}

export async function saveSatellite(
  satelliteName: string,
  selectedProduct: SelectedProductPayload
): Promise<SaveSatelliteResponse> {
  const url = `${API_BASE_URL}/api/satellites/save`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ satelliteName, selectedProduct }),
  });
  return parseJsonOrThrow<SaveSatelliteResponse>(response);
}

export interface SavedSatelliteSummary {
  id: string;
  satelliteName: string;
  mission: string;
  instrumentName: string | null;
  polarisation: string;
  sensingTime: string;
  size: string;
  preview: string | null;
  savedAt: string;
  fileStatus: "downloading" | "completed" | "failed" | null;
}

export interface SavedSatelliteDetail extends SavedSatelliteSummary {
  productId: string;
  directoryPath: string;
  summary: { label: string; value: string }[];
  product: { label: string; value: string }[];
  instrument: { label: string; value: string }[];
  platform: { label: string; value: string }[];
  other: { label: string; value: string }[];
  downloadSingleFile: string;
  footprint: Footprint;
  createdAt: string;
  updatedAt: string;
}

export async function fetchSavedSatellites(
  params: { name?: string; dateFrom?: string; dateUntil?: string; page?: number; pageSize?: number } = {}
): Promise<{ items: SavedSatelliteSummary[]; total: number; page: number; pageSize: number }> {
  const search = new URLSearchParams();
  if (params.name) search.set("name", params.name);
  if (params.dateFrom) search.set("dateFrom", params.dateFrom);
  if (params.dateUntil) search.set("dateUntil", params.dateUntil);
  search.set("page", String(params.page ?? 1));
  search.set("pageSize", String(params.pageSize ?? 10));
  const url = `${API_BASE_URL}/api/satellites?${search.toString()}`;
  const response = await fetch(url);
  return parseJsonOrThrow<{ items: SavedSatelliteSummary[]; total: number; page: number; pageSize: number }>(
    response
  );
}

export async function fetchSavedSatelliteDetail(id: string): Promise<SavedSatelliteDetail> {
  const url = `${API_BASE_URL}/api/satellites/${encodeURIComponent(id)}`;
  const response = await fetch(url);
  return parseJsonOrThrow<SavedSatelliteDetail>(response);
}

export async function deleteSavedSatellite(id: string): Promise<{ success: boolean; message: string }> {
  const url = `${API_BASE_URL}/api/satellites/${encodeURIComponent(id)}`;
  const response = await fetch(url, { method: "DELETE" });
  return parseJsonOrThrow<{ success: boolean; message: string }>(response);
}

export async function retryFileDownload(id: string): Promise<{ success: boolean; message: string }> {
  const url = `${API_BASE_URL}/api/satellites/${encodeURIComponent(id)}/retry-file-download`;
  const response = await fetch(url, { method: "POST" });
  return parseJsonOrThrow<{ success: boolean; message: string }>(response);
}

export function getSavedSatelliteThumbnailUrl(previewPath: string): string {
  return `${API_BASE_URL}/${previewPath}`;
}

export function getSavedSatelliteDownloadFileUrl(id: string): string {
  return `${API_BASE_URL}/api/satellites/${encodeURIComponent(id)}/download-file`;
}

export interface LandslideJob {
  id: string;
  name: string;
  preSatelliteId: string;
  postSatelliteId: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;
  message: string | null;
  stage: string | null;
  stageIndex: number;
  totalStages: number;
  thresholdDb: number;
  hasResult: boolean;
  createdAt: string;
  updatedAt: string;
}

export async function processLandslide(
  preSatelliteId: string,
  postSatelliteId: string,
  aoi?: [number, number, number, number],
): Promise<LandslideJob> {
  const url = `${API_BASE_URL}/api/landslide/process`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preSatelliteId, postSatelliteId, aoi }),
  });
  return parseJsonOrThrow<LandslideJob>(response);
}

export async function fetchLandslideJobs(): Promise<{ items: LandslideJob[]; total: number }> {
  const url = `${API_BASE_URL}/api/landslide/jobs`;
  const response = await fetch(url);
  return parseJsonOrThrow<{ items: LandslideJob[]; total: number }>(response);
}

export async function deleteLandslideJob(id: string): Promise<{ success: boolean }> {
  const url = `${API_BASE_URL}/api/landslide/jobs/${encodeURIComponent(id)}`;
  const response = await fetch(url, { method: "DELETE" });
  return parseJsonOrThrow<{ success: boolean }>(response);
}

export function getLandslideResultUrl(id: string): string {
  return `${API_BASE_URL}/api/landslide/jobs/${encodeURIComponent(id)}/result`;
}

export function getLandslidePreviewImageUrl(id: string): string {
  return `${API_BASE_URL}/api/landslide/jobs/${encodeURIComponent(id)}/preview.png`;
}

export function getLandslideKmzUrl(id: string): string {
  return `${API_BASE_URL}/api/landslide/jobs/${encodeURIComponent(id)}/kmz`;
}

// bounds = [south, west, north, east]
export async function fetchLandslidePreview(id: string): Promise<{ bounds: [number, number, number, number] }> {
  const url = `${API_BASE_URL}/api/landslide/jobs/${encodeURIComponent(id)}/preview`;
  const response = await fetch(url);
  return parseJsonOrThrow<{ bounds: [number, number, number, number] }>(response);
}

export interface ActivityLogEntry {
  id: string;
  action: string;
  category: string;
  status: "in_progress" | "completed" | "failed";
  description: string;
  progress: number;
  createdAt: string;
}

export async function fetchActivityLogs(): Promise<{ items: ActivityLogEntry[]; total: number }> {
  const url = `${API_BASE_URL}/api/logs`;
  const response = await fetch(url);
  return parseJsonOrThrow<{ items: ActivityLogEntry[]; total: number }>(response);
}
