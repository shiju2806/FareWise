import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  onSubmit: (data: {
    name: string;
    destination_city: string;
    start_date: string;
    end_date: string;
    notes?: string;
    member_emails?: string[];
  }) => Promise<void>;
  loading: boolean;
}

export function GroupTripCreate({ onSubmit, loading }: Props) {
  const [name, setName] = useState("");
  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [notes, setNotes] = useState("");
  const [emails, setEmails] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await onSubmit({
      name,
      destination_city: destination,
      start_date: startDate,
      end_date: endDate,
      notes: notes || undefined,
      member_emails: emails
        ? emails.split(",").map((e) => e.trim()).filter(Boolean)
        : undefined,
    });
    setName("");
    setDestination("");
    setStartDate("");
    setEndDate("");
    setNotes("");
    setEmails("");
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Create Group Trip</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input
            placeholder="Trip name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <Input
            placeholder="Destination city"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            required
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />
            <Input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              required
            />
          </div>
          <textarea
            className="w-full border rounded-md px-3 py-2 text-sm bg-background"
            placeholder="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
          />
          <Input
            placeholder="Invite by email (comma-separated)"
            value={emails}
            onChange={(e) => setEmails(e.target.value)}
          />
          <Button type="submit" disabled={loading || !name || !destination || !startDate || !endDate}>
            {loading ? "Creating..." : "Create Group Trip"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
