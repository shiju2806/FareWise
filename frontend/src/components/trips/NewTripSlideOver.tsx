import { useState } from "react";
import { TripChat } from "@/components/trip/TripChat";
import { StructuredTripForm } from "@/components/trip/StructuredTripForm";
import { useTripStore, type LegInput } from "@/stores/tripStore";
import { useTripChatStore } from "@/stores/tripChatStore";

type Mode = "chat" | "form";

interface Props {
  open: boolean;
  onClose: () => void;
  onTripCreated: (tripId: string) => void;
}

export function NewTripSlideOver({ open, onClose, onTripCreated }: Props) {
  const [mode, setMode] = useState<Mode>("chat");
  const { loading, createTripStructured } = useTripStore();
  const resetChat = useTripChatStore((s) => s.reset);

  if (!open) return null;

  function handleClose() {
    resetChat();
    onClose();
  }

  async function handleFormSubmit(legs: LegInput[]) {
    const trip = await createTripStructured(legs);
    if (trip) {
      onTripCreated(trip.id);
      handleClose();
    }
  }

  function handleChatTripCreated(tripId: string) {
    onTripCreated(tripId);
    handleClose();
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[1px] transition-opacity"
        onClick={handleClose}
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 z-50 w-[400px] bg-background border-l border-border shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold">Plan a Trip</h3>
          <div className="flex items-center gap-2">
            {/* Mode toggle */}
            <div className="flex rounded-md border border-border overflow-hidden">
              <button
                type="button"
                onClick={() => setMode("chat")}
                className={`px-2 py-1 text-[11px] font-medium transition-colors ${
                  mode === "chat"
                    ? "bg-primary text-primary-foreground"
                    : "bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                Chat
              </button>
              <button
                type="button"
                onClick={() => setMode("form")}
                className={`px-2 py-1 text-[11px] font-medium transition-colors ${
                  mode === "form"
                    ? "bg-primary text-primary-foreground"
                    : "bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                Form
              </button>
            </div>
            <button
              type="button"
              onClick={handleClose}
              className="p-1 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden p-3">
          {mode === "chat" ? (
            <TripChat onTripCreated={handleChatTripCreated} />
          ) : (
            <div className="overflow-y-auto h-full">
              <StructuredTripForm onSubmit={handleFormSubmit} loading={loading} />
            </div>
          )}
        </div>
      </div>
    </>
  );
}
