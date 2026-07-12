import { useEffect, useMemo, useRef, useState } from "react";
import {
  deleteLandslideJob,
  deleteSavedSatellite,
  fetchLandslideJobs,
  fetchLandslidePreview,
  fetchSavedSatelliteDetail,
  fetchSavedSatellites,
  getLandslideKmzUrl,
  getLandslidePreviewImageUrl,
  getLandslideResultUrl,
  getSavedSatelliteDownloadFileUrl,
  getSavedSatelliteThumbnailUrl,
  processLandslide,
  retryFileDownload,
  type LandslideJob,
  type SavedSatelliteDetail,
  type SavedSatelliteSummary,
} from "@/api/client";
import type { LandslideOverlay } from "@/components/SavedSatelliteMap";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DateField } from "@/components/FilterPanel";
import SavedProductInfoModal from "@/components/SavedProductInfoModal";
import SavedSatelliteMap from "@/components/SavedSatelliteMap";
import { useLanguage } from "@/context/LanguageContext";
import type { TranslationKey } from "@/i18n/translations";
import { Check, CheckSquare, Circle, Download, Eye, EyeOff, Info, Loader2, MapPin, MapPinOff, Mountain, RefreshCw, Square, Trash2 } from "lucide-react";

const PAGE_SIZE = 10;
const NAME_DEBOUNCE_MS = 300;

const FILE_STATUS_LABEL_KEY: Record<string, TranslationKey> = {
  downloading: "fileStatusDownloading",
  completed: "fileStatusCompleted",
  failed: "fileStatusFailed",
};

const FILE_STATUS_BADGE_CLASS: Record<string, string> = {
  downloading: "bg-muted text-muted-foreground",
  completed: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
};

const LANDSLIDE_STATUS_LABEL_KEY: Record<string, TranslationKey> = {
  pending: "landslideStatusPending",
  processing: "landslideStatusProcessing",
  completed: "landslideStatusCompleted",
  failed: "landslideStatusFailed",
};

const LANDSLIDE_STAGE_KEYS: TranslationKey[] = [
  "landslideStage1",
  "landslideStage2",
  "landslideStage3",
  "landslideStage4",
  "landslideStage5",
  "landslideStage6",
  "landslideStage7",
];

const LANDSLIDE_STATUS_BADGE_CLASS: Record<string, string> = {
  pending: "bg-muted text-muted-foreground",
  processing: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  completed: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
};

function SavedSatellitePage() {
  const { t } = useLanguage();
  const [items, setItems] = useState<SavedSatelliteSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [nameInput, setNameInput] = useState("");
  const [name, setName] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateUntil, setDateUntil] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<SavedSatelliteDetail | null>(null);
  const [infoModalItem, setInfoModalItem] = useState<SavedSatelliteDetail | null>(null);
  const detailCache = useRef(new Map<string, SavedSatelliteDetail>());
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [jobs, setJobs] = useState<LandslideJob[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [aoiInput, setAoiInput] = useState("");
  const [previewJobId, setPreviewJobId] = useState<string | null>(null);
  const [landslideOverlay, setLandslideOverlay] = useState<LandslideOverlay | null>(null);

  const handleTogglePreview = async (jobId: string) => {
    if (previewJobId === jobId) {
      setPreviewJobId(null);
      setLandslideOverlay(null);
      return;
    }
    try {
      const { bounds } = await fetchLandslidePreview(jobId);
      const [south, west, north, east] = bounds;
      setLandslideOverlay({
        url: getLandslidePreviewImageUrl(jobId),
        bounds: [
          [south, west],
          [north, east],
        ],
      });
      setPreviewJobId(jobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("landslidePreviewFailed"));
    }
  };

  // Parse "minLon,minLat,maxLon,maxLat" -> tuple, or null if empty/invalid.
  const parseAoi = (raw: string): [number, number, number, number] | null => {
    const parts = raw.split(",").map((p) => Number(p.trim()));
    if (parts.length !== 4 || parts.some((n) => Number.isNaN(n))) return null;
    const [minLon, minLat, maxLon, maxLat] = parts;
    if (minLon >= maxLon || minLat >= maxLat) return null;
    return [minLon, minLat, maxLon, maxLat];
  };

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  const loadJobs = async () => {
    try {
      const { items } = await fetchLandslideJobs();
      setJobs(items);
    } catch {
      // Jobs panel is secondary; a failed poll should not surface a page-level error.
    }
  };

  useEffect(() => {
    loadJobs();
  }, []);

  // Poll while any job is still running so progress/status updates live.
  useEffect(() => {
    const active = jobs.some((job) => job.status === "pending" || job.status === "processing");
    if (!active) return;
    const timer = setInterval(loadJobs, 4000);
    return () => clearInterval(timer);
  }, [jobs]);

  const toggleSelected = (id: string) => {
    setSelectedIds((current) => {
      if (current.includes(id)) return current.filter((x) => x !== id);
      if (current.length >= 2) return current; // cap at a pre/post pair
      return [...current, id];
    });
  };

  const handleProcessLandslide = async () => {
    if (selectedIds.length !== 2) {
      setError(t("landslideNeedTwo"));
      return;
    }
    const trimmed = aoiInput.trim();
    let aoi: [number, number, number, number] | undefined;
    if (trimmed) {
      const parsed = parseAoi(trimmed);
      if (!parsed) {
        setError(t("landslideAoiInvalid"));
        return;
      }
      aoi = parsed;
    }
    // No AOI = full ~250 km scene = very slow (~20 min, GBs). Make the user confirm.
    if (!aoi && !window.confirm(t("landslideNoAoiConfirm"))) {
      return;
    }
    setIsProcessing(true);
    setError(null);
    try {
      await processLandslide(selectedIds[0], selectedIds[1], aoi);
      setSelectedIds([]);
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("landslideStartFailed"));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDeleteJob = async (id: string) => {
    if (!window.confirm(t("landslideDeleteJobConfirm"))) return;
    try {
      await deleteLandslideJob(id);
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("landslideStartFailed"));
    }
  };

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const { items: fetched, total: fetchedTotal } = await fetchSavedSatellites({
        name: name || undefined,
        dateFrom: dateFrom || undefined,
        dateUntil: dateUntil || undefined,
        page,
        pageSize: PAGE_SIZE,
      });
      setItems(fetched);
      setTotal(fetchedTotal);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loadingSavedSatellites"));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [name, dateFrom, dateUntil, page]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setName(nameInput);
      setPage(1);
    }, NAME_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [nameInput]);

  const handleDateFromChange = (value: string) => {
    setDateFrom(value);
    setPage(1);
  };

  const handleDateUntilChange = (value: string) => {
    setDateUntil(value);
    setPage(1);
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm(t("deleteSatelliteConfirm"))) return;
    try {
      await deleteSavedSatellite(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("satelliteDeleteFailed"));
    }
  };

  const handleRetry = async (id: string) => {
    try {
      await retryFileDownload(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("fileStatusFailed"));
    }
  };

  const getDetail = async (id: string): Promise<SavedSatelliteDetail | null> => {
    const cached = detailCache.current.get(id);
    if (cached) return cached;
    try {
      const detail = await fetchSavedSatelliteDetail(id);
      detailCache.current.set(id, detail);
      return detail;
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loadingSavedSatellites"));
      return null;
    }
  };

  const handleViewOnMap = async (id: string) => {
    if (selectedDetail?.id === id) {
      setSelectedDetail(null);
      return;
    }
    const detail = await getDetail(id);
    if (detail) setSelectedDetail(detail);
  };

  const handleProductInfo = async (id: string) => {
    const detail = await getDetail(id);
    if (detail) setInfoModalItem(detail);
  };

  return (
    <main className="flex flex-1 gap-3 overflow-hidden p-3">
      <div className="flex w-1/2 flex-col overflow-hidden rounded-xl border bg-background shadow-sm">
        <div className="flex flex-col gap-3 border-b p-4">
          <h1 className="text-xl font-semibold">{t("savedSatellitesTitle")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("savedSatellitesSubtitle")}
          </p>

          <div className="flex flex-col gap-2 rounded-lg border border-dashed bg-muted/30 p-2">
            <div className="flex items-center gap-2">
              <Mountain className="h-4 w-4 shrink-0 text-muted-foreground" />
              <p className="min-w-0 flex-1 text-[11px] text-muted-foreground">
                {t("landslideSelectHint")}
              </p>
              <span className="shrink-0 text-[11px] text-muted-foreground">{selectedIds.length}/2</span>
              <Button
                type="button"
                size="sm"
                disabled={selectedIds.length !== 2 || isProcessing}
                onClick={handleProcessLandslide}
                className="h-7 shrink-0 px-2 text-[11px]"
              >
                <Mountain className="h-3 w-3" /> {t("landslideProcess")}
              </Button>
            </div>
            <Input
              value={aoiInput}
              onChange={(event) => setAoiInput(event.target.value)}
              placeholder={t("landslideAoiPlaceholder")}
              className="h-7 text-[11px]"
            />
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex flex-col gap-1 sm:max-w-xs">
              <Label htmlFor="search-satellite">
                {t("searchSatelliteNameSearch")}
              </Label>

              <Input
                id="search-satellite"
                placeholder={t("searchSatelliteName")}
                value={nameInput}
                onChange={(event) => setNameInput(event.target.value)}
              />
            </div>
            <DateField
              id="saved-satellite-date-from"
              label={t("dateFrom")}
              placeholder={t("dateFrom")}
              value={dateFrom}
              onChange={handleDateFromChange}
            />
            <DateField
              id="saved-satellite-date-until"
              label={t("dateUntil")}
              placeholder={t("dateUntil")}
              value={dateUntil}
              onChange={handleDateUntilChange}
            />
          </div>
        </div>

        <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
          {isLoading && <p className="text-sm text-muted-foreground">{t("loadingSavedSatellites")}</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!isLoading && items.length === 0 && (
            <p className="text-sm text-muted-foreground">{t("noSavedSatellites")}</p>
          )}

          <div className="flex flex-col gap-3">
            {items.map((item) => (
              <Card key={item.id} className="flex gap-2 rounded-lg p-3 shadow-sm transition-colors hover:border-primary/40">
                {item.preview && (
                  <img
                    src={getSavedSatelliteThumbnailUrl(item.preview)}
                    alt={item.satelliteName}
                    className="h-16 w-16 shrink-0 rounded-md object-cover"
                  />
                )}
                <CardContent className="min-w-0 flex-1 p-0">
                  <h3 className="break-all text-sm font-semibold">{item.satelliteName}</h3>
                  {item.fileStatus && (
                    <span
                      className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[10px] ${FILE_STATUS_BADGE_CLASS[item.fileStatus] ?? ""
                        }`}
                    >
                      {t(FILE_STATUS_LABEL_KEY[item.fileStatus] ?? "fileStatusDownloading")}
                    </span>
                  )}
                  <dl className="mt-1 grid grid-cols-2 gap-x-1 text-[11px] text-muted-foreground">
                    <dt>{t("mission")}</dt>
                    <dd>{item.mission}</dd>
                    <dt>{t("polarisation")}</dt>
                    <dd>{item.polarisation}</dd>
                    <dt>{t("sensingTime")}</dt>
                    <dd>{item.sensingTime}</dd>
                    <dt>{t("size")}</dt>
                    <dd>{item.size}</dd>
                  </dl>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <Button
                      type="button"
                      size="sm"
                      variant={item.id === selectedDetail?.id ? "secondary" : "default"}
                      onClick={() => handleViewOnMap(item.id)}
                      className="h-7 flex-1 px-2 text-[11px]"
                    >
                      {item.id === selectedDetail?.id ? (
                        <>
                          <MapPinOff className="h-3 w-3" /> {t("removeFromMap")}
                        </>
                      ) : (
                        <>
                          <MapPin className="h-3 w-3" /> {t("viewOnMap")}
                        </>
                      )}
                    </Button>
                    {item.fileStatus === "completed" && (
                      <Button
                        type="button"
                        size="sm"
                        variant={selectedIds.includes(item.id) ? "secondary" : "outline"}
                        onClick={() => toggleSelected(item.id)}
                        disabled={!selectedIds.includes(item.id) && selectedIds.length >= 2}
                        className="h-7 px-2 text-[11px]"
                      >
                        {selectedIds.includes(item.id) ? (
                          <>
                            <CheckSquare className="h-3 w-3" /> {t("landslideSelected")}
                          </>
                        ) : (
                          <>
                            <Square className="h-3 w-3" /> {t("landslideSelect")}
                          </>
                        )}
                      </Button>
                    )}
                    {item.fileStatus === "completed" ? (
                      <Button asChild type="button" size="sm" variant="outline" className="h-7 flex-1 px-2 text-[11px]">
                        <a href={getSavedSatelliteDownloadFileUrl(item.id)} download>
                          <Download className="h-3 w-3" /> {t("download")}
                        </a>
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled
                        title={t("downloadNotReady")}
                        className="h-7 flex-1 px-2 text-[11px]"
                      >
                        <Download className="h-3 w-3" /> {t("download")}
                      </Button>
                    )}
                    {item.fileStatus === "failed" && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => handleRetry(item.id)}
                        className="h-7 px-2 text-[11px]"
                      >
                        <RefreshCw className="h-3 w-3" /> {t("retryFileDownload")}
                      </Button>
                    )}
                    <Button
                      type="button"
                      size="icon"
                      variant="outline"
                      aria-label={t("delete")}
                      onClick={() => handleDelete(item.id)}
                      className="h-7 w-7 shrink-0"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="outline"
                      aria-label={t("productInfo")}
                      onClick={() => handleProductInfo(item.id)}
                      className="h-7 w-7 shrink-0"
                    >
                      <Info className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {jobs.length > 0 && (
            <div className="mt-2 flex flex-col gap-2 border-t pt-3">
              <h2 className="text-sm font-semibold">{t("landslideJobsTitle")}</h2>
              {jobs.map((job) => (
                <Card key={job.id} className="rounded-lg p-3 shadow-sm">
                  <CardContent className="p-0">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="break-all text-xs font-medium">{job.name}</h3>
                      <span
                        className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${LANDSLIDE_STATUS_BADGE_CLASS[job.status] ?? ""}`}
                      >
                        {t(LANDSLIDE_STATUS_LABEL_KEY[job.status] ?? "landslideStatusPending")}
                      </span>
                    </div>
                    {(job.status === "processing" || job.status === "completed") && (
                      <div className="mt-2 flex flex-col gap-1.5">
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div className="h-full bg-primary transition-all" style={{ width: `${job.progress}%` }} />
                        </div>
                        <ol className="flex flex-col gap-1">
                          {LANDSLIDE_STAGE_KEYS.map((key, idx) => {
                            const done = job.status === "completed" || idx < job.stageIndex;
                            const active = job.status === "processing" && idx === job.stageIndex;
                            return (
                              <li
                                key={key}
                                className={`flex items-center gap-1.5 text-[11px] ${
                                  done
                                    ? "text-green-600 dark:text-green-400"
                                    : active
                                      ? "font-medium text-foreground"
                                      : "text-muted-foreground"
                                }`}
                              >
                                {done ? (
                                  <Check className="h-3 w-3 shrink-0" />
                                ) : active ? (
                                  <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
                                ) : (
                                  <Circle className="h-3 w-3 shrink-0" />
                                )}
                                <span>
                                  {t("landslideStep")} {idx + 1}: {t(key)}
                                </span>
                              </li>
                            );
                          })}
                        </ol>
                      </div>
                    )}
                    {job.status === "failed" && job.message && (
                      <p className="mt-1 text-[11px] text-destructive">{job.message}</p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {job.hasResult ? (
                        <>
                          <Button
                            type="button"
                            size="sm"
                            variant={previewJobId === job.id ? "secondary" : "outline"}
                            onClick={() => handleTogglePreview(job.id)}
                            className="h-7 flex-1 px-2 text-[11px]"
                          >
                            {previewJobId === job.id ? (
                              <>
                                <EyeOff className="h-3 w-3" /> {t("landslideHidePreview")}
                              </>
                            ) : (
                              <>
                                <Eye className="h-3 w-3" /> {t("landslidePreview")}
                              </>
                            )}
                          </Button>
                          <Button asChild type="button" size="sm" variant="outline" className="h-7 flex-1 px-2 text-[11px]">
                            <a href={getLandslideResultUrl(job.id)} download>
                              <Download className="h-3 w-3" /> {t("landslideDownloadResult")}
                            </a>
                          </Button>
                          <Button asChild type="button" size="sm" variant="outline" className="h-7 flex-1 px-2 text-[11px]">
                            <a href={getLandslideKmzUrl(job.id)} download>
                              <Download className="h-3 w-3" /> {t("landslideDownloadKmz")}
                            </a>
                          </Button>
                        </>
                      ) : (
                        <span className="flex-1" />
                      )}
                      <Button
                        type="button"
                        size="icon"
                        variant="outline"
                        aria-label={t("delete")}
                        onClick={() => handleDeleteJob(job.id)}
                        className="h-7 w-7 shrink-0"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>

        {total > 0 && (
          <div className="flex items-center justify-center gap-3 border-t p-3">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={page <= 1}
              onClick={() => setPage((current) => current - 1)}
            >
              {t("paginationPrev")}
            </Button>
            <span className="text-xs text-muted-foreground">
              {page} / {totalPages}
            </span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={page >= totalPages}
              onClick={() => setPage((current) => current + 1)}
            >
              {t("paginationNext")}
            </Button>
          </div>
        )}
      </div>

      <div className="w-1/2 overflow-hidden rounded-xl border">
        <SavedSatelliteMap selected={selectedDetail} overlay={landslideOverlay} />
      </div>

      {infoModalItem && (
        <SavedProductInfoModal
          item={infoModalItem}
          open={infoModalItem !== null}
          onOpenChange={(open) => {
            if (!open) setInfoModalItem(null);
          }}
        />
      )}
    </main>
  );
}

export default SavedSatellitePage;
