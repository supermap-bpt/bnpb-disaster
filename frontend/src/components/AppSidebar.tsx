import { Bookmark, Clock, Globe, Settings, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useLanguage } from "@/context/LanguageContext";
import type { TranslationKey } from "@/i18n/translations";

const NAV_ITEMS: { key: TranslationKey; icon: typeof Globe; active: boolean }[] = [
  { key: "navSatelliteExplorer", icon: Globe, active: true },
  { key: "navSavedSatellite", icon: Bookmark, active: false },
  { key: "navHistory", icon: Clock, active: false },
  { key: "navSettings", icon: Settings, active: false },
];

function AppSidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useLanguage();

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-[1450] bg-black/40 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-[1500] flex w-60 shrink-0 transform flex-col border-r bg-background transition-transform duration-200 md:static md:z-auto md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-14 items-center justify-between border-b px-4 md:hidden">
          <span className="text-sm font-semibold">{t("menu")}</span>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label={t("closeMenu")}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV_ITEMS.map(({ key, icon: Icon, active }) => (
            <button
              key={key}
              type="button"
              disabled={!active}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-transparent"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {t(key)}
            </button>
          ))}
        </nav>

        <Separator />
        <div className="p-3 text-xs text-muted-foreground">Esri Indonesia</div>
      </aside>
    </>
  );
}

export default AppSidebar;
