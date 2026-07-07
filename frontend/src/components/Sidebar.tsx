import { useGIS } from "../context/GISContext";
import { fetchSearch } from "../api/client";
import SearchBar from "./SearchBar";
import FilterPanel from "./FilterPanel";
import ProductCard from "./ProductCard";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useLanguage } from "@/context/LanguageContext";

function Sidebar() {
  const {
    searchResults,
    searchTotal,
    placeRing,
    lastSearchFilter,
    appendSearchResults,
    isSearching,
    setIsSearching,
    setError,
  } = useGIS();
  const { t } = useLanguage();

  const hasMore = searchResults.length < searchTotal;

  const handleLoadMore = async () => {
    if (!lastSearchFilter || !placeRing) return;
    setError(null);
    setIsSearching(true);
    try {
      const { results, total } = await fetchSearch(
        lastSearchFilter,
        placeRing,
        searchResults.length
      );
      appendSearchResults(results, total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loadMoreFailed"));
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex shrink-0 flex-col gap-3 overflow-y-auto p-3">
        <h1 className="text-xl font-semibold z-[1000]">{t("findSatelliteTitle")}</h1>
        <p className="text-sm text-muted-foreground z-[1000]">{t("findSatelliteSubtitle")}</p>
        <SearchBar />
        <FilterPanel />
      </div>

      <div className="shrink-0 border-y px-3 py-2 text-sm font-medium text-foreground">
        {searchTotal > 0
          ? t("showingResults", { count: searchResults.length, total: searchTotal })
          : t("searchResults")}
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3">
          {searchResults.length === 0 && (
            <p className="p-3 text-center text-sm text-muted-foreground">{t("noResultsYet")}</p>
          )}

          <div className="flex flex-col gap-2">
            {searchResults.map((item) => (
              <ProductCard key={item.id} item={item} />
            ))}
          </div>

          {hasMore && (
            <Button
              type="button"
              variant="outline"
              onClick={handleLoadMore}
              disabled={isSearching}
              className="mt-2 w-full"
            >
              {isSearching ? t("loading") : t("loadMore")}
            </Button>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

export default Sidebar;
