import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "@/context/LanguageContext";
import { ActivityNotificationsProvider } from "@/context/ActivityNotificationsContext";
import { PreDisasterMenuProvider } from "@/context/PreDisasterMenuContext";
import Header from "./Header";

vi.mock("@/api/client", () => ({
  fetchActivityLogs: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { fetchActivityLogs } from "@/api/client";

function Providers({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <LanguageProvider>
        <ActivityNotificationsProvider>
          <PreDisasterMenuProvider>{children}</PreDisasterMenuProvider>
        </ActivityNotificationsProvider>
      </LanguageProvider>
    </MemoryRouter>
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

beforeEach(() => {
  vi.mocked(fetchActivityLogs).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

async function renderWithOneCompletedNotification() {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(fetchActivityLogs)
    .mockResolvedValueOnce({ items: [IN_PROGRESS_ITEM], total: 1 })
    .mockResolvedValueOnce({ items: [COMPLETED_ITEM], total: 1 });

  render(
    <Providers>
      <Header />
    </Providers>
  );

  await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(1));
  vi.advanceTimersByTime(2000);
  await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalledTimes(2));
}

describe("Header notifications bell", () => {
  it("shows no unread badge when there are no notifications", async () => {
    vi.mocked(fetchActivityLogs).mockResolvedValue({ items: [], total: 0 });

    render(
      <Providers>
        <Header />
      </Providers>
    );

    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalled());
    expect(screen.queryByTestId("notifications-badge")).not.toBeInTheDocument();
  });

  it("shows an unread badge after a tracked operation completes", async () => {
    await renderWithOneCompletedNotification();
    expect(await screen.findByTestId("notifications-badge")).toHaveTextContent("1");
  });

  it("lists real notifications in the dropdown instead of the empty placeholder", async () => {
    await renderWithOneCompletedNotification();

    const bellButton = screen.getByRole("button", { name: /notifikasi/i });
    fireEvent.pointerDown(bellButton, { button: 0, ctrlKey: false });
    fireEvent.click(bellButton);

    expect(await screen.findByText(/download product/i)).toBeInTheDocument();
    expect(screen.queryByText(/tidak ada notifikasi baru/i)).not.toBeInTheDocument();
  });

  it("clears the unread badge when the dropdown is opened", async () => {
    await renderWithOneCompletedNotification();
    expect(await screen.findByTestId("notifications-badge")).toBeInTheDocument();

    const bellButton = screen.getByRole("button", { name: /notifikasi/i });
    fireEvent.pointerDown(bellButton, { button: 0, ctrlKey: false });
    fireEvent.click(bellButton);

    await waitFor(() => expect(screen.queryByTestId("notifications-badge")).not.toBeInTheDocument());
  });
});
