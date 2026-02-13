import { useState } from "react";
import { Button } from "@/components/ui/button";
import apiClient from "@/api/client";

interface Props {
  tripId: string;
  type: "savings" | "audit";
}

export function ExportButton({ tripId, type }: Props) {
  const [loading, setLoading] = useState(false);

  async function handleExport() {
    setLoading(true);
    try {
      const url =
        type === "savings"
          ? `/reports/savings/${tripId}/pdf`
          : `/reports/audit/${tripId}/pdf`;
      const res = await apiClient.get(url, { responseType: "blob" });
      const blobUrl = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `${type}_${tripId}.pdf`;
      a.click();
      window.URL.revokeObjectURL(blobUrl);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={handleExport} disabled={loading}>
      {loading ? "Generating..." : `Export ${type === "savings" ? "Savings" : "Audit"} PDF`}
    </Button>
  );
}
