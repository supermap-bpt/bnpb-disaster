import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { saveSatelliteSchema, type SaveSatelliteFormValues } from "../schemas/saveSatelliteSchema";
import type { SearchResultItem } from "../context/GISContext";
import { fetchProductAttributes, saveSatellite } from "../api/client";
import { getInstrument, getMission } from "@/lib/satellite";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useLanguage } from "@/context/LanguageContext";

function SaveSatelliteModal({
  item,
  open,
  onOpenChange,
}: {
  item: SearchResultItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useLanguage();
  const [isSaving, setIsSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<SaveSatelliteFormValues>({
    resolver: zodResolver(saveSatelliteSchema),
    defaultValues: { satelliteName: "" },
  });

  useEffect(() => {
    if (!open) {
      reset({ satelliteName: "" });
      setSuccessMessage(null);
    }
  }, [open, reset]);

  const onSubmit = async (values: SaveSatelliteFormValues) => {
    setIsSaving(true);
    setSuccessMessage(null);
    try {
      const attributes = await fetchProductAttributes(item.id);
      const result = await saveSatellite(values.satelliteName, {
        id: item.id,
        name: item.name,
        mission: getMission(item.productType),
        instrumentName: getInstrument(item.productType),
        polarisation: item.polarisation,
        sensingTime: item.sensingTime,
        size: item.size,
        footprint: item.footprint,
        attributes,
      });
      if (!result.success) {
        setError("satelliteName", { type: "manual", message: result.message });
        return;
      }
      setSuccessMessage(result.message);
    } catch (err) {
      setError("satelliteName", {
        type: "manual",
        message: err instanceof Error ? err.message : t("satelliteSaveFailed"),
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("saveSatelliteModalTitle")}</DialogTitle>
        </DialogHeader>

        {successMessage ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-foreground">{successMessage}</p>
            <Button type="button" onClick={() => onOpenChange(false)} className="w-full">
              {t("cancel")}
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="satelliteName" className="text-sm font-medium">
                {t("satelliteNameLabel")}
              </label>
              <Input
                id="satelliteName"
                type="text"
                placeholder={t("satelliteNamePlaceholder")}
                disabled={isSaving}
                {...register("satelliteName")}
              />
              {errors.satelliteName && (
                <p className="text-xs text-destructive">{errors.satelliteName.message}</p>
              )}
            </div>

            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                className="flex-1"
                disabled={isSaving}
                onClick={() => onOpenChange(false)}
              >
                {t("cancel")}
              </Button>
              <Button type="submit" className="flex-1" disabled={isSaving}>
                {isSaving ? t("saving") : t("save")}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default SaveSatelliteModal;
