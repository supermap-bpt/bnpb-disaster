import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { LanguageProvider } from "@/context/LanguageContext";
import LogsPage from "./LogsPage";

vi.mock("@/api/client", () => ({
  fetchActivityLogs: vi.fn(),
}));

import { fetchActivityLogs } from "@/api/client";

function Providers({ children }: { children: ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}

const IN_PROGRESS_ITEM = {
  id: "log-1",
  action: "Save Satellite",
  category: "Satellite",
  status: "in_progress" as const,
  description: 'Saving satellite "Test"',
  progress: 30,
  createdAt: "2026-07-02T10:00:00Z",
};

const COMPLETED_ITEM = {
  ...IN_PROGRESS_ITEM,
  id: "log-2",
  status: "completed" as const,
  progress: 100,
};

const FAILED_ITEM = {
  ...IN_PROGRESS_ITEM,
  id: "log-3",
  status: "failed" as const,
};

beforeEach(() => {
  vi.mocked(fetchActivityLogs).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("LogsPage", () => {
  it("shows the empty state when there are no logs", async () => {
    vi.mocked(fetchActivityLogs).mockResolvedValue({ items: [], total: 0 });

    render(
      <Providers>
        <LogsPage />
      </Providers>
    );

    expect(await screen.findByText(/belum ada log aktivitas/i)).toBeInTheDocument();
  });

  it("lists logs with their status badges", async () => {
    vi.mocked(fetchActivityLogs).mockResolvedValue({
      items: [IN_PROGRESS_ITEM, COMPLETED_ITEM, FAILED_ITEM],
      total: 3,
    });

    render(
      <Providers>
        <LogsPage />
      </Providers>
    );

    expect(await screen.findAllByText("Save Satellite")).toHaveLength(3);
    expect(screen.getByText("Sedang Berlangsung")).toBeInTheDocument();
    expect(screen.getByText("Selesai")).toBeInTheDocument();
    expect(screen.getByText("Gagal")).toBeInTheDocument();
  });

  it("polls again while a log is in progress", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchActivityLogs)
      .mockResolvedValueOnce({ items: [IN_PROGRESS_ITEM], total: 1 })
      .mockResolvedValueOnce({ items: [COMPLETED_ITEM], total: 1 });

    render(
      <Providers>
        <LogsPage />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));

    vi.advanceTimersByTime(2000);

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(2));
  });

  it("does not schedule another poll once every log is terminal", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchActivityLogs).mockResolvedValue({ items: [COMPLETED_ITEM], total: 1 });

    render(
      <Providers>
        <LogsPage />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));

    vi.advanceTimersByTime(5000);

    expect(fetchActivityLogs).toHaveBeenCalledTimes(1);
  });

  it("shows the numeric percent next to the bar only while in progress", async () => {
    vi.mocked(fetchActivityLogs).mockResolvedValue({
      items: [IN_PROGRESS_ITEM, COMPLETED_ITEM],
      total: 2,
    });

    render(
      <Providers>
        <LogsPage />
      </Providers>
    );

    expect(await screen.findByText("30%")).toBeInTheDocument();
    expect(screen.queryByText("100%")).not.toBeInTheDocument();
  });
});
