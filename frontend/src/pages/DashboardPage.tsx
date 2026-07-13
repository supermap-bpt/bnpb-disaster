import { Link } from "react-router-dom";
import { AlertTriangle, Clock, Globe, TrendingUp } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useLanguage } from "@/context/LanguageContext";
import { usePreDisasterMenu } from "@/context/PreDisasterMenuContext";
import type { TranslationKey } from "@/i18n/translations";

const SIMPLE_DASHBOARD_CARDS: {
  path: string;
  icon: typeof Globe;
  titleKey: TranslationKey;
  descKey: TranslationKey;
}[] = [
    {
      path: "/satellite-explorer",
      icon: Globe,
      titleKey: "navFindSatellite",
      descKey: "findSatelliteDesc",
    },
    {
      path: "/during-disaster",
      icon: AlertTriangle,
      titleKey: "navDuringDisaster",
      descKey: "duringDisasterDesc",
    },
    {
      path: "/prediction-disaster",
      icon: TrendingUp,
      titleKey: "navPredictionDisaster",
      descKey: "predictionDisasterDesc",
    },
  ];

function DashboardPage() {
  const { t } = useLanguage();
  const { setIsOpen: setPreDisasterMenuOpen } = usePreDisasterMenu();

  return (
    <main className="flex-1 overflow-y-auto p-6">
      <h1 className="text-2xl font-semibold">{t("welcomeTitle")}</h1>
      <p className="mt-1 text-muted-foreground">{t("welcomeSubtitle")}</p>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">

        {/* Find Satellite */}
        <Link
          to={SIMPLE_DASHBOARD_CARDS[0].path}
        >
          <Card className="h-full transition-colors hover:border-primary/40">
            <CardHeader>
              <Globe className="h-6 w-6 text-primary" />
              <CardTitle className="mt-2">
                {t(SIMPLE_DASHBOARD_CARDS[0].titleKey)}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription>
                {t(SIMPLE_DASHBOARD_CARDS[0].descKey)}
              </CardDescription>
            </CardContent>
          </Card>
        </Link>

        {/* Pre Disaster */}
        <Card
          role="button"
          tabIndex={0}
          onClick={() => setPreDisasterMenuOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setPreDisasterMenuOpen(true);
            }
          }}
          className="h-full cursor-pointer text-left transition-colors hover:border-primary/40"
        >
          <CardHeader>
            <Clock className="h-6 w-6 text-primary" />
            <CardTitle className="mt-2">{t("navPreDisaster")}</CardTitle>
          </CardHeader>
          <CardContent>
            <CardDescription>{t("preDisasterDesc")}</CardDescription>
          </CardContent>
        </Card>

        {/* During & Prediction */}
        {SIMPLE_DASHBOARD_CARDS.slice(1).map(({ path, icon: Icon, titleKey, descKey }) => (
          <Link key={path} to={path}>
            <Card className="h-full transition-colors hover:border-primary/40">
              <CardHeader>
                <Icon className="h-6 w-6 text-primary" />
                <CardTitle className="mt-2">{t(titleKey)}</CardTitle>
              </CardHeader>
              <CardContent>
                <CardDescription>{t(descKey)}</CardDescription>
              </CardContent>
            </Card>
          </Link>
        ))}

      </div>
    </main>
  );
}

export default DashboardPage;
