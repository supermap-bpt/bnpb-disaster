import { useLanguage } from "@/context/LanguageContext";
import type { TranslationKey } from "@/i18n/translations";

function PlaceholderPage({ titleKey }: { titleKey: TranslationKey }) {
  const { t } = useLanguage();

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-1 p-6 text-center">
      <h1 className="text-xl font-semibold">{t(titleKey)}</h1>
      <p className="text-muted-foreground">{t("comingSoonPageBody")}</p>
    </main>
  );
}

export default PlaceholderPage;
