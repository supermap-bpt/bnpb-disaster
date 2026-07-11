import { useState } from "react";
import { useGIS, type SearchResultItem } from "../context/GISContext";
import { getDownloadUrl, getPreviewImageUrl } from "../api/client";
import { getInstrument, getMission, hasPreview, isDemnas, isSentinel2, isSentinel3 } from "@/lib/satellite";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Bookmark, Download, ImageOff, Info, MapPin, MapPinOff } from "lucide-react";
import { useLanguage } from "@/context/LanguageContext";
import ProductInfoModal from "./ProductInfoModal";
import SaveSatelliteModal from "./SaveSatelliteModal";

const PRODUCT_TYPE_LABEL: Record<string, string> = {
  SENTINEL_1_SLC: "Level 1-SLC",
  SENTINEL_1_GRD: "Level 1-GRD",
  SENTINEL_2_L1C: "L1C",
  SENTINEL_2_L2A: "L2A",
  SENTINEL_3_SLSTR_L2_LST: "Level-2 LST",
  SENTINEL_3_SLSTR_L2_WST: "Level-2 WST",
  DEMNAS_25K: "25K",
  DEMNAS_50K: "50K",
};

const DEMNAS_PORTAL_URL = "https://tanahair.indonesia.go.id/portal-web/unduh/demnas";

function demnasYearLabel(sensingTime: string): string {
  const year = sensingTime.slice(0, 4);
  return year === "0001" ? "-" : year;
}

function ProductCard({ item }: { item: SearchResultItem }) {
  const { selectedProductId, selectProduct, setHoveredProductId } = useGIS();
  const { t } = useLanguage();
  const isSelected = item.id === selectedProductId;
  const [imageFailed, setImageFailed] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const showThumbnail = hasPreview(item.productType) && !imageFailed;

  return (
    <Card
      data-testid={`card-${item.id}`}
      onMouseEnter={() => setHoveredProductId(item.id)}
      onMouseLeave={() => setHoveredProductId(null)}
      className={cn(
        "flex gap-2 p-2 transition-colors",
        isSelected ? "border-primary bg-primary/5" : "hover:border-primary/40"
      )}
    >
      {showThumbnail ? (
        <img
          src={getPreviewImageUrl(item.id)}
          alt={item.name}
          onError={() => setImageFailed(true)}
          className="h-16 w-16 shrink-0 rounded-md object-cover"
        />
      ) : (
        <div className="flex h-16 w-16 shrink-0 flex-col items-center justify-center gap-1 rounded-md bg-muted text-center text-[10px] text-muted-foreground">
          <ImageOff className="h-4 w-4" />
          {t("noPreview")}
        </div>
      )}

      <CardContent className="min-w-0 flex-1 p-0">
        <h3 className="break-all text-xs font-semibold">{item.name}</h3>
        <dl className="mt-1 grid grid-cols-2 gap-x-1 text-[11px] text-muted-foreground">
          <dt>{t("mission")}</dt>
          <dd>{getMission(item.productType)}</dd>
          <dt>{t("instrument")}</dt>
          <dd>{getInstrument(item.productType)}</dd>
          <dt>{t("type")}</dt>
          <dd>{PRODUCT_TYPE_LABEL[item.productType] ?? item.productType}</dd>
          {isDemnas(item.productType) || isSentinel3(item.productType) ? null : isSentinel2(item.productType) ? (
            <>
              <dt>{t("cloudCover")}</dt>
              <dd>{item.cloudCoverPercentage != null ? `${Math.round(item.cloudCoverPercentage)}%` : "N/A"}</dd>
            </>
          ) : (
            <>
              <dt>{t("polarisation")}</dt>
              <dd>{item.polarisation}</dd>
            </>
          )}
          <dt>{t("sensingTime")}</dt>
          <dd>{isDemnas(item.productType) ? demnasYearLabel(item.sensingTime) : item.sensingTime}</dd>
          <dt>{t("size")}</dt>
          <dd>{item.size}</dd>
        </dl>

        <div className="mt-2 flex gap-1.5">
          <Button
            type="button"
            size="sm"
            variant={isSelected ? "secondary" : "default"}
            onClick={() => selectProduct(isSelected ? null : item.id)}
            className="h-7 flex-1 px-2 text-[11px]"
          >
            {isSelected ? (
              <>
                <MapPinOff className="h-3 w-3" /> {t("removeFromMap")}
              </>
            ) : (
              <>
                <MapPin className="h-3 w-3" /> {t("viewOnMap")}
              </>
            )}
          </Button>
          <Button asChild type="button" size="sm" variant="outline" className="h-7 flex-1 px-2 text-[11px]">
            {isDemnas(item.productType) ? (
              <a href={DEMNAS_PORTAL_URL} target="_blank" rel="noopener noreferrer">
                <Download className="h-3 w-3" /> {t("download")}
              </a>
            ) : (
              <a href={getDownloadUrl(item.id)} download>
                <Download className="h-3 w-3" /> {t("download")}
              </a>
            )}
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            aria-label={t("save")}
            onClick={() => setSaveModalOpen(true)}
            className="h-7 w-7 shrink-0"
          >
            <Bookmark className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            aria-label={t("info")}
            onClick={() => setInfoOpen(true)}
            className="h-7 w-7 shrink-0"
          >
            <Info className="h-3.5 w-3.5" />
          </Button>
        </div>

        <ProductInfoModal item={item} open={infoOpen} onOpenChange={setInfoOpen} />
        <SaveSatelliteModal item={item} open={saveModalOpen} onOpenChange={setSaveModalOpen} />

        <div className="mt-1 flex gap-2 text-[10px] text-muted-foreground/70">
          <button type="button" disabled title={t("comingSoon")} className="cursor-not-allowed">
            {t("metadata")}
          </button>
          <button type="button" disabled title={t("comingSoon")} className="cursor-not-allowed">
            {t("workspace")}
          </button>
          <button type="button" disabled title={t("comingSoon")} className="cursor-not-allowed">
            {t("favorite")}
          </button>
        </div>
      </CardContent>
    </Card>
  );
}

export default ProductCard;
