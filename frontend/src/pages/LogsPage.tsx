import { useEffect, useRef, useState } from "react";
import { fetchActivityLogs, type ActivityLogEntry } from "@/api/client";
import { useLanguage } from "@/context/LanguageContext";
import type { TranslationKey } from "@/i18n/translations";

const POLL_INTERVAL_MS = 2000;

const STATUS_LABEL_KEY: Record<string, TranslationKey> = {
  in_progress: "statusInProgress",
  completed: "statusCompleted",
  failed: "statusFailed",
};

const STATUS_BADGE_CLASS: Record<string, string> = {
  in_progress: "bg-muted text-muted-foreground",
  completed: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
};

function LogsPage() {
  const { t } = useLanguage();
  const [items, setItems] = useState<ActivityLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = async () => {
    try {
      const { items: fetched } = await fetchActivityLogs();
      setItems(fetched);
      setError(null);
      if (fetched.some((item) => item.status === "in_progress")) {
        timeoutRef.current = setTimeout(load, POLL_INTERVAL_MS);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("noLogs"));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return (
    <main className="flex-1 overflow-y-auto p-6">
      <h1 className="mb-4 text-xl font-semibold">{t("logsTitle")}</h1>

      {isLoading && <p className="text-sm text-muted-foreground">{t("loading")}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!isLoading && items.length === 0 && <p className="text-sm text-muted-foreground">{t("noLogs")}</p>}

      {items.length > 0 && (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="py-2 pr-3 font-medium">{t("logsTimestamp")}</th>
              <th className="py-2 pr-3 font-medium">{t("logsAction")}</th>
              <th className="py-2 pr-3 font-medium">{t("logsCategory")}</th>
              <th className="py-2 pr-3 font-medium">{t("logsStatus")}</th>
              <th className="py-2 pr-3 font-medium">{t("logsDescription")}</th>
              <th className="py-2 font-medium">{t("logsProgress")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-b last:border-b-0">
                <td className="py-2 pr-3 text-xs text-muted-foreground">{item.createdAt}</td>
                <td className="py-2 pr-3">{item.action}</td>
                <td className="py-2 pr-3">{item.category}</td>
                <td className="py-2 pr-3">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${STATUS_BADGE_CLASS[item.status] ?? ""}`}
                  >
                    {t(STATUS_LABEL_KEY[item.status] ?? "statusInProgress")}
                  </span>
                </td>
                <td className="py-2 pr-3 text-muted-foreground">{item.description}</td>
                <td className="py-2">
                  {item.status === "in_progress" ? (
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
                          style={{ width: `${item.progress}%` }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground">{item.progress}%</span>
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {item.status === "completed" ? "✓" : "×"}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

export default LogsPage;
