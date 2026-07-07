import type { SavedSatelliteDetail } from "../api/client";
import { getSavedSatelliteDownloadFileUrl, getSavedSatelliteThumbnailUrl } from "../api/client";
import { useLanguage } from "@/context/LanguageContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Download } from "lucide-react";
import Section from "@/components/product-info/Section";
import AttributeTable from "@/components/product-info/AttributeTable";
import FootprintPreview from "@/components/product-info/FootprintPreview";

function SavedProductInfoModal({
  item,
  open,
  onOpenChange,
}: {
  item: SavedSatelliteDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useLanguage();
  const isFileReady = item.fileStatus === "completed";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl w-[95vw] p-0 overflow-hidden rounded-xl">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle className="text-xl font-semibold">{t("productInfo")}</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-8 p-6">
          <div className="max-h-[70vh] overflow-y-auto pr-2">
            <Section title="Summary" defaultOpen>
              <AttributeTable rows={item.summary} />
            </Section>
            <Section title="Product">
              <AttributeTable rows={item.product} />
            </Section>
            <Section title="Instrument">
              <AttributeTable rows={item.instrument} />
            </Section>
            <Section title="Platform">
              <AttributeTable rows={item.platform} />
            </Section>
            {item.other.length > 0 && (
              <Section title="Other">
                <AttributeTable rows={item.other} />
              </Section>
            )}
            <Section title="Download single files">
              {isFileReady ? (
                <a
                  href={getSavedSatelliteDownloadFileUrl(item.id)}
                  download
                  className="flex w-full items-start gap-3 rounded-md border p-3 text-sm transition-colors hover:bg-muted"
                >
                  <Download className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <p className="break-all font-medium text-primary">{item.downloadSingleFile}</p>
                  </div>
                </a>
              ) : (
                <p className="text-xs text-muted-foreground" title={t("downloadNotReady")}>
                  {t("downloadNotReady")}
                </p>
              )}
            </Section>
          </div>

          <div className="flex flex-col gap-4">
            <div>
              <h3 className="mb-1.5 text-sm font-semibold">Preview</h3>
              {item.preview ? (
                <img
                  src={getSavedSatelliteThumbnailUrl(item.preview)}
                  alt={item.satelliteName}
                  className="h-64 w-full rounded-lg border object-cover shadow-sm"
                />
              ) : (
                <div className="flex h-40 w-full items-center justify-center rounded-md border bg-muted text-xs text-muted-foreground">
                  {t("noPreviewAvailable")}
                </div>
              )}
            </div>

            <div>
              <h3 className="mb-1.5 text-sm font-semibold">Footprint</h3>
              <FootprintPreview footprint={item.footprint} />
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default SavedProductInfoModal;
