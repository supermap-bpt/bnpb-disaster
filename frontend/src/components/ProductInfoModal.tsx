import { useEffect, useState } from "react";
import type { SearchResultItem } from "../context/GISContext";
import { fetchProductAttributes, getDownloadUrl, getPreviewImageUrl, type ProductAttribute } from "../api/client";
import { useLanguage } from "@/context/LanguageContext";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Download } from "lucide-react";
import { cn } from "@/lib/utils";
import Section from "@/components/product-info/Section";
import AttributeTable from "@/components/product-info/AttributeTable";
import FootprintPreview from "@/components/product-info/FootprintPreview";

// Real, documented CDSE/Copernicus catalogue Attribute "Name" identifiers,
// grouped to mirror Copernicus Browser's own Product Info popup sections
// (Summary / Product / Instrument / Platform). Unmapped attributes CDSE
// actually returns still show up under "Other" - never silently dropped.
const PRODUCT_FIELDS: { name: string; label: string }[] = [
  { name: "orbitNumber", label: "Absolute orbit number" },
  { name: "beginningDateTime", label: "Beginning date time" },
  { name: "cloudCover", label: "Cloud cover" },
  { name: "completionTimeFromAscendingNode", label: "Completion time from ascending node" },
  { name: "cycleNumber", label: "Cycle number" },
  { name: "dataTakeID", label: "Data take id" },
  { name: "endingDateTime", label: "Ending date time" },
  { name: "instrumentConfigurationID", label: "Instrument configuration id" },
  { name: "modificationDate", label: "Modification date" },
  { name: "operationalMode", label: "Operational mode" },
  { name: "orbitDirection", label: "Orbit direction" },
  { name: "origin", label: "Origin" },
  { name: "originDate", label: "Origin date" },
  { name: "polarisationChannels", label: "Polarisation channels" },
  { name: "processingCenter", label: "Processing center" },
  { name: "processingDate", label: "Processing date" },
  { name: "processingLevel", label: "Processing level" },
  { name: "processorName", label: "Processor name" },
  { name: "processorVersion", label: "Processor version" },
  { name: "productClass", label: "Product class" },
  { name: "productComposition", label: "Product composition" },
  { name: "productType", label: "Product type" },
  { name: "publicationDate", label: "Publication date" },
  { name: "relativeOrbitNumber", label: "Relative orbit number" },
  { name: "s3Path", label: "S3 path" },
  { name: "segmentStartTime", label: "Segment start time" },
  { name: "sliceNumber", label: "Slice number" },
  { name: "sliceProductFlag", label: "Slice product flag" },
  { name: "startTimeFromAscendingNode", label: "Start time from ascending node" },
  { name: "swathIdentifier", label: "Swath identifier" },
  { name: "timeliness", label: "Timeliness" },
  { name: "totalSlices", label: "Total slices" },
];

const INSTRUMENT_FIELDS: { name: string; label: string }[] = [
  { name: "instrumentShortName", label: "Instrument short name" },
];

const PLATFORM_FIELDS: { name: string; label: string }[] = [
  { name: "platformShortName", label: "Platform short name" },
  { name: "platformSerialIdentifier", label: "Platform serial identifier" },
];

const MAPPED_NAMES = new Set(
  [...PRODUCT_FIELDS, ...INSTRUMENT_FIELDS, ...PLATFORM_FIELDS].map((field) => field.name)
);

function lookup(attributes: ProductAttribute[], name: string): string | undefined {
  return attributes.find((attr) => attr.name === name)?.value;
}

function ProductInfoModal({
  item,
  open,
  onOpenChange,
}: {
  item: SearchResultItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useLanguage();
  const [attributes, setAttributes] = useState<ProductAttribute[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const showThumbnail =
    (item.productType === "SENTINEL_1_GRD" ||
      item.productType === "SENTINEL_2_L2A" ||
      item.productType === "SENTINEL_3_SLSTR_L2_LST") &&
    !imageFailed;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchProductAttributes(item.id)
      .then((result) => {
        if (!cancelled) setAttributes(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t("attributesFailed"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, item.id]);

  const productRows = PRODUCT_FIELDS.map(({ name, label }) => ({ name, label, value: lookup(attributes, name) })).filter(
    (row): row is { name: string; label: string; value: string } => row.value !== undefined
  );
  const instrumentRows = INSTRUMENT_FIELDS.map(({ name, label }) => ({
    label,
    value: lookup(attributes, name),
  })).filter((row): row is { label: string; value: string } => row.value !== undefined);
  const platformRows = PLATFORM_FIELDS.map(({ name, label }) => ({
    label,
    value: lookup(attributes, name),
  })).filter((row): row is { label: string; value: string } => row.value !== undefined);
  const otherRows = attributes
    .filter((attr) => !MAPPED_NAMES.has(attr.name))
    .map((attr) => ({ label: attr.name, value: attr.value }));

  const summaryRows = [
    { label: "Name", value: item.name },
    { label: "Size", value: item.size },
    { label: "Sensing time", value: item.sensingTime },
    ...platformRows.filter((row) => row.label === "Platform short name"),
    ...instrumentRows.filter((row) => row.label === "Instrument short name"),
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl w-[95vw] p-0 overflow-hidden rounded-xl">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle className="text-xl font-semibold">
            {t("productInfo")}
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-8 p-6">
          <div className="max-h-[70vh] overflow-y-auto pr-2">
            {loading && <p className="py-2 text-xs text-muted-foreground">{t("loadingAttributes")}</p>}
            {error && <p className="py-2 text-xs text-destructive">{error}</p>}

            <Section title="Summary" defaultOpen>
              <AttributeTable rows={summaryRows} />
            </Section>
            <Section title="Product">
              <AttributeTable rows={productRows} />
            </Section>
            <Section title="Instrument">
              <AttributeTable rows={instrumentRows} />
            </Section>
            <Section title="Platform">
              <AttributeTable rows={platformRows} />
            </Section>
            {otherRows.length > 0 && (
              <Section title="Other">
                <AttributeTable rows={otherRows} />
              </Section>
            )}
            <Section title="Download single files">
              <a
                href={getDownloadUrl(item.id)}
                download
                className="flex w-full items-start gap-3 rounded-md border p-3 text-sm transition-colors hover:bg-muted"
              >
                <Download className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div className="min-w-0 flex-1">
                  <p className="break-all font-medium text-primary">
                    {item.name}
                  </p>
                </div>
              </a>
            </Section>
          </div>

          <div className="flex flex-col gap-4">
            <div>
              <h3 className="mb-1.5 text-sm font-semibold">Preview</h3>
              {showThumbnail ? (
                <img
                  src={getPreviewImageUrl(item.id)}
                  alt={item.name}
                  onError={() => setImageFailed(true)}
                  className={cn("h-64 w-full rounded-lg border object-cover shadow-sm")}
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

export default ProductInfoModal;
