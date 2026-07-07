import { z } from "zod";

export const saveSatelliteSchema = z.object({
  satelliteName: z
    .string()
    .trim()
    .min(1, "Nama satelit wajib diisi")
    .max(100, "Nama satelit maksimal 100 karakter"),
});

export type SaveSatelliteFormValues = z.infer<typeof saveSatelliteSchema>;
