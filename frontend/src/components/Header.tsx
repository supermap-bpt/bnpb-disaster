import { Link, useLocation } from "react-router-dom";
import {
  AlertTriangle,
  Bell,
  Check,
  ChevronDown,
  Clock,
  Globe,
  Languages,
  LayoutDashboard,
  Moon,
  ScrollText,
  Satellite,
  Sun,
  TrendingUp,
  UserPlus,
} from "lucide-react";
import SearchBar from "./SearchBar";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "@/hooks/useTheme";
import { useLanguage } from "@/context/LanguageContext";
import { useActivityNotifications } from "@/context/ActivityNotificationsContext";
import { cn } from "@/lib/utils";
import type { TranslationKey } from "@/i18n/translations";

const SIMPLE_NAV_ITEMS: { path: string; key: TranslationKey; icon: typeof LayoutDashboard }[] = [
  { path: "/during-disaster", key: "navDuringDisaster", icon: AlertTriangle },
  { path: "/prediction-disaster", key: "navPredictionDisaster", icon: TrendingUp },
];

function navButtonClass(active: boolean) {
  return cn(
    "flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium outline-none transition-colors",
    active
      ? "bg-primary text-primary-foreground shadow-sm"
      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
  );
}

function Header() {
  const { theme, toggleTheme } = useTheme();
  const { language, setLanguage, t } = useLanguage();
  const { pathname } = useLocation();
  const { notifications, unreadCount, markAllRead } = useActivityNotifications();
  const preDisasterActive = pathname === "/pre-disaster/landslide" || pathname === "/pre-disaster/flood";

  return (
    <header className="sticky top-0 z-[1600] flex shrink-0 flex-col border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex h-14 items-center gap-3 px-4">
        <div className="flex items-center gap-2 font-semibold">
          <Satellite className="h-5 w-5 text-primary" />
          <span className="hidden sm:inline">Disaster Management Dashboard</span>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="icon"
            className="rounded-full"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? t("enableLightMode") : t("enableDarkMode")}
          >
            {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="rounded-full" aria-label={t("language")}>
                <Languages className="h-5 w-5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{t("language")}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setLanguage("id")}>
                {language === "id" && <Check className="h-4 w-4" />}
                {t("languageId")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setLanguage("en")}>
                {language === "en" && <Check className="h-4 w-4" />}
                {t("languageEn")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu onOpenChange={(open) => open && markAllRead()}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="relative rounded-full"
                aria-label={t("notifications")}
              >
                <Bell className="h-5 w-5" />
                {unreadCount > 0 && (
                  <span
                    data-testid="notifications-badge"
                    className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-destructive-foreground"
                  >
                    {unreadCount}
                  </span>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{t("notifications")}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {notifications.length === 0 ? (
                <DropdownMenuItem disabled>{t("noNotifications")}</DropdownMenuItem>
              ) : (
                notifications.map((item) => (
                  <DropdownMenuItem
                    key={item.id}
                    disabled
                    className="flex flex-col items-start gap-0.5 whitespace-normal"
                  >
                    <span className="text-sm font-medium">
                      {item.status === "completed" ? "✓" : "×"} {item.action}
                    </span>
                    <span className="text-xs text-muted-foreground">{item.description}</span>
                  </DropdownMenuItem>
                ))
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-9 w-9 rounded-full p-0">
                <Avatar className="h-9 w-9">
                  <AvatarFallback>U</AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{t("account")}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled>{t("profile")}</DropdownMenuItem>
              <DropdownMenuItem disabled>{t("settings")}</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <nav className="flex items-center gap-1 overflow-x-auto border-t px-4 py-1.5">
        <Link to="/" className={navButtonClass(pathname === "/")}>
          <LayoutDashboard className="h-4 w-4 shrink-0" />
          {t("navDashboard")}
        </Link>

        <Link to="/satellite-explorer" className={navButtonClass(pathname === "/satellite-explorer")}>
          <Globe className="h-4 w-4 shrink-0" />
          {t("navSatelliteExplorer")}
        </Link>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className={navButtonClass(preDisasterActive)}>
              <Clock className="h-4 w-4 shrink-0" />
              {t("navPreDisaster")}
              <ChevronDown className="h-3.5 w-3.5 shrink-0" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem asChild>
              <Link to="/pre-disaster/landslide">{t("navLandslide")}</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/pre-disaster/flood">{t("navFlood")}</Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {SIMPLE_NAV_ITEMS.map(({ path, key, icon: Icon }) => (
          <Link key={path} to={path} className={navButtonClass(pathname === path)}>
            <Icon className="h-4 w-4 shrink-0" />
            {t(key)}
          </Link>
        ))}

        <Link to="/logs" className={navButtonClass(pathname === "/logs")}>
          <ScrollText className="h-4 w-4 shrink-0" />
          {t("navLogs")}
        </Link>
      </nav>
    </header>
  );
}

export default Header;
