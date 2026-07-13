import { z } from "zod";

const productTypeEnum = z.enum([
  "SENTINEL_1_SLC",
  "SENTINEL_1_GRD",
  "SENTINEL_2_L1C",
  "SENTINEL_2_L2A",
  "SENTINEL_3_SLSTR_L2_LST",
  "SENTINEL_3_SLSTR_L2_WST",
  "DEMNAS_25K",
  "DEMNAS_50K",
]);

export function isDemnasOnly(productType: string[]): boolean {
  return productType.length > 0 && productType.every((value) => value.startsWith("DEMNAS"));
}

export const filterSchema = z
  .object({
    productType: z.array(productTypeEnum).min(1, "Pilih minimal satu data source"),
    cloudCoverMax: z.number().min(0).max(100).default(100),
    // DEMNAS is a fixed historical baseline, not a time series - dateFrom/dateUntil
    // aren't required when it's the only family selected (see superRefine below).
    dateFrom: z.string(),
    dateUntil: z.string(),
  })
  .superRefine((data, ctx) => {
    if (isDemnasOnly(data.productType)) return;

    if (!data.dateFrom) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Tanggal 'Dari' wajib diisi", path: ["dateFrom"] });
    }
    if (!data.dateUntil) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Tanggal 'Sampai' wajib diisi", path: ["dateUntil"] });
    }
    if (data.dateFrom && data.dateUntil && data.dateUntil < data.dateFrom) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Tanggal 'Sampai' tidak boleh mendahului tanggal 'Dari'",
        path: ["dateUntil"],
      });
    }
  });

export type FilterFormValues = z.infer<typeof filterSchema>;
export type ProductType = z.infer<typeof productTypeEnum>;
