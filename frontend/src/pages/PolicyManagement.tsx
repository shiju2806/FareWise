import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePolicyStore } from "@/stores/policyStore";
import { useAuthStore } from "@/stores/authStore";

const RULE_TYPES = [
  { value: "max_price", label: "Maximum Price" },
  { value: "advance_booking", label: "Advance Booking" },
  { value: "cabin_restriction", label: "Cabin Restriction" },
  { value: "preferred_airline", label: "Preferred Airline" },
  { value: "max_stops", label: "Maximum Stops" },
  { value: "approval_threshold", label: "Auto-Approval Threshold" },
];

const ACTION_TYPES = [
  { value: "block", label: "Block" },
  { value: "warn", label: "Warn" },
  { value: "flag_for_review", label: "Flag for Review" },
  { value: "info", label: "Info" },
];

function PolicyForm({
  onSubmit,
  onCancel,
  initial,
}: {
  onSubmit: (data: Record<string, unknown>) => void;
  onCancel: () => void;
  initial?: Record<string, unknown>;
}) {
  const [name, setName] = useState((initial?.name as string) || "");
  const [description, setDescription] = useState(
    (initial?.description as string) || ""
  );
  const [ruleType, setRuleType] = useState(
    (initial?.rule_type as string) || "max_price"
  );
  const [action, setAction] = useState(
    (initial?.action as string) || "warn"
  );
  const [severity, setSeverity] = useState(
    (initial?.severity as number) || 5
  );
  const [thresholdJson, setThresholdJson] = useState(
    JSON.stringify(initial?.threshold || {}, null, 2)
  );
  const [conditionsJson, setConditionsJson] = useState(
    JSON.stringify(initial?.conditions || {}, null, 2)
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      onSubmit({
        name,
        description,
        rule_type: ruleType,
        action,
        severity,
        threshold: JSON.parse(thresholdJson),
        conditions: JSON.parse(conditionsJson),
      });
    } catch {
      alert("Invalid JSON in threshold or conditions");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-1">Name</label>
        <input
          className="w-full border rounded-md px-3 py-2 text-sm bg-background"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">Description</label>
        <textarea
          className="w-full border rounded-md px-3 py-2 text-sm bg-background"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">Rule Type</label>
          <select
            className="w-full border rounded-md px-3 py-2 text-sm bg-background"
            value={ruleType}
            onChange={(e) => setRuleType(e.target.value)}
          >
            {RULE_TYPES.map((rt) => (
              <option key={rt.value} value={rt.value}>
                {rt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Action</label>
          <select
            className="w-full border rounded-md px-3 py-2 text-sm bg-background"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          >
            {ACTION_TYPES.map((at) => (
              <option key={at.value} value={at.value}>
                {at.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">
          Severity (1-10)
        </label>
        <input
          type="number"
          min={1}
          max={10}
          className="w-24 border rounded-md px-3 py-2 text-sm bg-background"
          value={severity}
          onChange={(e) => setSeverity(Number(e.target.value))}
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">
          Threshold (JSON)
        </label>
        <textarea
          className="w-full border rounded-md px-3 py-2 text-sm font-mono bg-background"
          value={thresholdJson}
          onChange={(e) => setThresholdJson(e.target.value)}
          rows={3}
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">
          Conditions (JSON)
        </label>
        <textarea
          className="w-full border rounded-md px-3 py-2 text-sm font-mono bg-background"
          value={conditionsJson}
          onChange={(e) => setConditionsJson(e.target.value)}
          rows={3}
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit">{initial ? "Update" : "Create"}</Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

const actionColors: Record<string, string> = {
  block: "bg-red-100 text-red-800",
  warn: "bg-amber-100 text-amber-800",
  flag_for_review: "bg-orange-100 text-orange-800",
  info: "bg-blue-100 text-blue-800",
};

export default function PolicyManagement() {
  const { policies, loading, fetch, create, update, remove } =
    usePolicyStore();
  const user = useAuthStore((s) => s.user);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const isAdmin = user?.role === "admin";

  const handleCreate = async (data: Record<string, unknown>) => {
    await create(data as Parameters<typeof create>[0]);
    setShowForm(false);
  };

  const handleUpdate = async (data: Record<string, unknown>) => {
    if (editing) {
      await update(editing, data);
      setEditing(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">
            Travel Policies
          </h2>
          <p className="text-muted-foreground mt-1">
            {isAdmin
              ? "Manage company travel policies and compliance rules."
              : "View active company travel policies."}
          </p>
        </div>
        {isAdmin && !showForm && !editing && (
          <Button onClick={() => setShowForm(true)}>Add Policy</Button>
        )}
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">New Policy</CardTitle>
          </CardHeader>
          <CardContent>
            <PolicyForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
            />
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-24 bg-muted animate-pulse rounded-lg"
            />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {policies.map((policy) => (
            <Card key={policy.id}>
              {editing === policy.id ? (
                <CardContent className="pt-6">
                  <PolicyForm
                    initial={policy as unknown as Record<string, unknown>}
                    onSubmit={handleUpdate}
                    onCancel={() => setEditing(null)}
                  />
                </CardContent>
              ) : (
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold">{policy.name}</h3>
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            actionColors[policy.action] || "bg-gray-100"
                          }`}
                        >
                          {policy.action}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Severity: {policy.severity}/10
                        </span>
                      </div>
                      {policy.description && (
                        <p className="text-sm text-muted-foreground">
                          {policy.description}
                        </p>
                      )}
                      <div className="flex gap-4 text-xs text-muted-foreground">
                        <span>
                          Type:{" "}
                          {
                            RULE_TYPES.find(
                              (r) => r.value === policy.rule_type
                            )?.label
                          }
                        </span>
                        <span>
                          Threshold:{" "}
                          {JSON.stringify(policy.threshold)}
                        </span>
                      </div>
                    </div>
                    {isAdmin && (
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setEditing(policy.id)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            if (
                              confirm(
                                `Disable policy "${policy.name}"?`
                              )
                            ) {
                              remove(policy.id);
                            }
                          }}
                        >
                          Disable
                        </Button>
                      </div>
                    )}
                  </div>
                </CardContent>
              )}
            </Card>
          ))}
          {policies.length === 0 && (
            <p className="text-center text-muted-foreground py-8">
              No policies configured.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
