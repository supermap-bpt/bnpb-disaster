import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { fetchActivityLogs, type ActivityLogEntry } from "@/api/client";
import { useLanguage } from "@/context/LanguageContext";

const IDLE_POLL_INTERVAL_MS = 10000;
const ACTIVE_POLL_INTERVAL_MS = 2000;
const MAX_NOTIFICATIONS = 5;

interface ActivityNotificationsContextValue {
  notifications: ActivityLogEntry[];
  unreadCount: number;
  markAllRead: () => void;
}

const ActivityNotificationsContext = createContext<ActivityNotificationsContextValue | null>(null);

export function ActivityNotificationsProvider({ children }: { children: ReactNode }) {
  const { t } = useLanguage();
  const [notifications, setNotifications] = useState<ActivityLogEntry[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const notifiedIdsRef = useRef<Set<string>>(new Set());
  const hasBaselineRef = useRef(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      let stillInProgress = false;
      try {
        const { items } = await fetchActivityLogs();
        if (cancelled) return;

        if (!hasBaselineRef.current) {
          for (const item of items) {
            if (item.status === "completed" || item.status === "failed") {
              notifiedIdsRef.current.add(item.id);
            }
          }
          hasBaselineRef.current = true;
        } else {
          const newlyTerminal = items.filter(
            (item) =>
              (item.status === "completed" || item.status === "failed") &&
              !notifiedIdsRef.current.has(item.id)
          );

          if (newlyTerminal.length > 0) {
            for (const item of newlyTerminal) {
              notifiedIdsRef.current.add(item.id);
              if (item.status === "completed") {
                toast.success(t("toastCompleted", { action: item.action, description: item.description }));
              } else {
                toast.error(t("toastFailed", { action: item.action, description: item.description }));
              }
            }
            setNotifications((prev) => [...newlyTerminal, ...prev].slice(0, MAX_NOTIFICATIONS));
            setUnreadCount((prev) => prev + newlyTerminal.length);
          }
        }

        stillInProgress = items.some((item) => item.status === "in_progress");
      } catch {
        // A failed poll must never surface to the user - just retry later.
      } finally {
        if (!cancelled) {
          timeoutRef.current = setTimeout(
            poll,
            stillInProgress ? ACTIVE_POLL_INTERVAL_MS : IDLE_POLL_INTERVAL_MS
          );
        }
      }
    };

    poll();

    return () => {
      cancelled = true;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [t]);

  const markAllRead = () => setUnreadCount(0);

  return (
    <ActivityNotificationsContext.Provider value={{ notifications, unreadCount, markAllRead }}>
      {children}
    </ActivityNotificationsContext.Provider>
  );
}

export function useActivityNotifications() {
  const ctx = useContext(ActivityNotificationsContext);
  if (ctx === null) {
    throw new Error("useActivityNotifications must be used within an ActivityNotificationsProvider");
  }
  return ctx;
}
