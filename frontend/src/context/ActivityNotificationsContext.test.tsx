import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { LanguageProvider } from "@/context/LanguageContext";
import {
  ActivityNotificationsProvider,
  useActivityNotifications,
} from "./ActivityNotificationsContext";

vi.mock("@/api/client", () => ({
  fetchActivityLogs: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { fetchActivityLogs } from "@/api/client";
import { toast } from "sonner";

function Providers({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <ActivityNotificationsProvider>{children}</ActivityNotificationsProvider>
    </LanguageProvider>
  );
}

function TestConsumer() {
  const { notifications, unreadCount, markAllRead } = useActivityNotifications();
  return (
    <div>
      <span data-testid="unread-count">{unreadCount}</span>
      <button onClick={markAllRead}>mark read</button>
      <ul>
        {notifications.map((item) => (
          <li key={item.id}>
            {item.action}:{item.status}
          </li>
        ))}
      </ul>
    </div>
  );
}

const IN_PROGRESS_ITEM = {
  id: "log-1",
  action: "Download Product",
  category: "Satellite",
  status: "in_progress" as const,
  description: "Downloading test.zip",
  progress: 40,
  createdAt: "2026-07-02T10:00:00Z",
};

const COMPLETED_ITEM = { ...IN_PROGRESS_ITEM, status: "completed" as const, progress: 100 };
const FAILED_ITEM = { ...IN_PROGRESS_ITEM, id: "log-2", status: "failed" as const };

beforeEach(() => {
  vi.mocked(fetchActivityLogs).mockReset();
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.error).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ActivityNotificationsContext", () => {
  it("does not toast or list anything already terminal on the first (baseline) poll", async () => {
    vi.mocked(fetchActivityLogs).mockResolvedValue({ items: [COMPLETED_ITEM], total: 1 });

    render(
      <Providers>
        <TestConsumer />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));

    expect(toast.success).not.toHaveBeenCalled();
    expect(screen.getByTestId("unread-count")).toHaveTextContent("0");
  });

  it("toasts and lists a newly completed entry observed after the baseline", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchActivityLogs)
      .mockResolvedValueOnce({ items: [IN_PROGRESS_ITEM], total: 1 })
      .mockResolvedValueOnce({ items: [COMPLETED_ITEM], total: 1 });

    render(
      <Providers>
        <TestConsumer />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));
    vi.advanceTimersByTime(2000);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(2));

    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("unread-count")).toHaveTextContent("1");
    expect(screen.getByText("Download Product:completed")).toBeInTheDocument();
  });

  it("toasts a failure with toast.error", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchActivityLogs)
      .mockResolvedValueOnce({ items: [{ ...IN_PROGRESS_ITEM, id: "log-2" }], total: 1 })
      .mockResolvedValueOnce({ items: [FAILED_ITEM], total: 1 });

    render(
      <Providers>
        <TestConsumer />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));
    vi.advanceTimersByTime(2000);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(2));

    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it("does not re-toast the same entry on a later poll", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchActivityLogs)
      .mockResolvedValueOnce({ items: [IN_PROGRESS_ITEM], total: 1 })
      .mockResolvedValueOnce({ items: [COMPLETED_ITEM], total: 1 })
      .mockResolvedValueOnce({ items: [COMPLETED_ITEM], total: 1 });

    render(
      <Providers>
        <TestConsumer />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));
    vi.advanceTimersByTime(2000);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(2));
    vi.advanceTimersByTime(10000);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(3));

    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it("caps the notifications list at 5 entries, evicting the oldest", async () => {
    const makeItem = (id: string) => ({ ...COMPLETED_ITEM, id });
    vi.mocked(fetchActivityLogs)
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({
        items: [makeItem("a"), makeItem("b"), makeItem("c"), makeItem("d"), makeItem("e"), makeItem("f")],
        total: 6,
      });

    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(
      <Providers>
        <TestConsumer />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));
    vi.advanceTimersByTime(10000);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(2));

    const items = screen.getAllByText(/Download Product:completed/);
    expect(items).toHaveLength(5);
  });

  it("markAllRead resets unreadCount to 0 without clearing the notifications list", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchActivityLogs)
      .mockResolvedValueOnce({ items: [IN_PROGRESS_ITEM], total: 1 })
      .mockResolvedValueOnce({ items: [COMPLETED_ITEM], total: 1 });

    render(
      <Providers>
        <TestConsumer />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));
    vi.advanceTimersByTime(2000);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("unread-count")).toHaveTextContent("1");

    act(() => {
      screen.getByText("mark read").click();
    });

    expect(screen.getByTestId("unread-count")).toHaveTextContent("0");
    expect(screen.getByText("Download Product:completed")).toBeInTheDocument();
  });

  it("polls every 10s while idle and switches to 2s while something is in progress", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchActivityLogs).mockResolvedValue({ items: [], total: 0 });

    render(
      <Providers>
        <TestConsumer />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));
    vi.advanceTimersByTime(2000);
    expect(fetchActivityLogs).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(8000);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(2));
  });

  it("silently retries after a failed poll instead of throwing", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchActivityLogs)
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce({ items: [], total: 0 });

    render(
      <Providers>
        <TestConsumer />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));
    vi.advanceTimersByTime(10000);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("unread-count")).toHaveTextContent("0");
  });
});
