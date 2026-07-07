import { z } from "zod";

const productTypeEnum = z.enum([
  "SENTINEL_1_SLC",
  "SENTINEL_1_GRD",
  "SENTINEL_2_L1C",
  "SENTINEL_2_L2A",
  "SENTINEL_3_SLSTR_L2_LST",
  "SENTINEL_3_SLSTR_L2_WST",
]);

export const filterSchema = z
  .object({
    productType: z.array(productTypeEnum).min(1, "Pilih minimal satu data source"),
    cloudCoverMax: z.number().min(0).max(100).default(100),
    dateFrom: z.string().min(1, "Tanggal 'Dari' wajib diisi"),
    dateUntil: z.string().min(1, "Tanggal 'Sampai' wajib diisi"),
  })
  .refine((data) => data.dateUntil >= data.dateFrom, {
    message: "Tanggal 'Sampai' tidak boleh mendahului tanggal 'Dari'",
    path: ["dateUntil"],
  });

export type FilterFormValues = z.infer<typeof filterSchema>;
export type ProductType = z.infer<typeof productTypeEnum>;
