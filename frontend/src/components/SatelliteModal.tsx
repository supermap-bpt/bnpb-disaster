import { useGIS, type SearchResultItem } from "../context/GISContext";
import { fetchPreview, getDownloadUrl } from "../api/client";

const PRODUCT_TYPE_LABEL: Record<string, string> = {
  SENTINEL_1_SLC: "Sentinel-1 C-SAR Level 1-SLC",
  SENTINEL_1_GRD: "Sentinel-1 C-SAR Level 1-GRD",
};

// GRD/SLC pairs from the same acquisition share (near-)identical footprints, so
// the later-rendered layer sits on top and intercepts every click - the user can
// never reach the one underneath. Instead of selecting a single clicked layer,
// surface every result whose footprint overlaps the same pass (sensingTime within
// this window) so both are reachable, mirroring Copernicus Browser's "Showing N
// results" picker for the same situation.
const RELATED_WINDOW_MS = 60_000;

export function findRelatedProducts(
  items: SearchResultItem[],
  anchor: SearchResultItem
): SearchResultItem[] {
  const anchorTime = new Date(anchor.sensingTime).getTime();
  return items.filter(
    (item) => Math.abs(new Date(item.sensingTime).getTime() - anchorTime) <= RELATED_WINDOW_MS
  );
}

function SatelliteModal() {
  const {
    searchResults,
    selectedProductId,
    selectProduct,
    setPreviewData,
    isPreviewLoading,
    setIsPreviewLoading,
    setError,
  } = useGIS();

  const anchor = searchResults.find((result) => result.id === selectedProductId);
  if (!anchor) return null;

  const relatedProducts = findRelatedProducts(searchResults, anchor);

  const handlePreview = async (productId: string) => {
    setIsPreviewLoading(true);
    setError(null);
    try {
      const preview = await fetchPreview(productId);
      setPreviewData(preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gagal memuat citra.");
    } finally {
      setIsPreviewLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/40">
      <div className="max-h-[80vh] w-96 overflow-y-auto rounded bg-white p-4 shadow-lg">
        <div className="mb-2 flex items-start justify-between">
          <h2 className="text-sm font-semibold">
            Menampilkan {relatedProducts.length} hasil
          </h2>
          <button
            type="button"
            onClick={() => selectProduct(null)}
            aria-label="Tutup"
            className="ml-2 shrink-0 text-gray-500 hover:text-gray-800"
          >
            &times;
          </button>
        </div>

        <div className="flex flex-col gap-3">
          {relatedProducts.map((item) => (
            <div key={item.id} className="rounded border p-2">
              <h3 className="break-all text-xs font-semibold">{item.name}</h3>
              <dl className="mt-1 grid grid-cols-2 gap-x-2 gap-y-1 text-xs text-gray-700">
                <dt className="font-medium">Data Source</dt>
                <dd>{PRODUCT_TYPE_LABEL[item.productType] ?? item.productType}</dd>
                <dt className="font-medium">Sensing Time</dt>
                <dd>{item.sensingTime}</dd>
                <dt className="font-medium">Ukuran</dt>
                <dd>{item.size}</dd>
                <dt className="font-medium">Polarisasi</dt>
                <dd>{item.polarisation}</dd>
              </dl>

              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => handlePreview(item.id)}
                  disabled={isPreviewLoading}
                  className="flex-1 rounded bg-blue-600 px-3 py-1 text-xs text-white disabled:opacity-50"
                >
                  {isPreviewLoading ? "Memuat..." : "Lihat di Peta"}
                </button>
                <a
                  href={getDownloadUrl(item.id)}
                  download
                  className="flex-1 rounded bg-green-600 px-3 py-1 text-center text-xs text-white"
                >
                  Unduh
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default SatelliteModal;
