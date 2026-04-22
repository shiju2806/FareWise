import { Button } from "@/components/ui/button";

interface Props {
  elapsed: number;
  onCancel: () => void;
}

export function SearchLoadingSkeleton({ elapsed, onCancel }: Props) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="text-sm font-medium">
            Searching flights...
            {elapsed > 0 && <span className="text-muted-foreground ml-1">({elapsed}s)</span>}
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={onCancel} className="text-xs">
          Cancel
        </Button>
      </div>

      <div className="flex items-center justify-between bg-muted/30 rounded-lg px-3 py-2">
        <div className="h-3 w-64 bg-muted animate-pulse rounded" />
        <div className="h-3 w-24 bg-muted animate-pulse rounded" />
      </div>

      <div className="rounded-lg bg-muted/20 p-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="h-4 w-28 bg-muted animate-pulse rounded" />
          <div className="h-3 w-44 bg-muted animate-pulse rounded" />
        </div>
        <div className="flex gap-2 overflow-x-auto pb-2">
          {Array.from({ length: 15 }).map((_, i) => (
            <div
              key={i}
              className="w-[72px] h-[88px] bg-muted/60 animate-pulse rounded-lg shrink-0"
            />
          ))}
        </div>
      </div>

      <div className="h-10 bg-muted/40 animate-pulse rounded-lg" />

      <div className="space-y-2">
        <div className="h-4 w-20 bg-muted animate-pulse rounded" />
        <div className="h-5 bg-muted/40 animate-pulse rounded-full" />
      </div>

      <div className="rounded-lg bg-muted/15 p-3 space-y-2">
        <div className="h-4 w-48 bg-muted animate-pulse rounded" />
        <div className="rounded-lg border border-border overflow-hidden">
          <div className="flex bg-muted/40">
            <div className="w-[120px] h-8 shrink-0 border-r border-border" />
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="w-[68px] h-8 shrink-0 flex items-center justify-center">
                <div className="h-3 w-12 bg-muted animate-pulse rounded" />
              </div>
            ))}
          </div>
          {Array.from({ length: 5 }).map((_, r) => (
            <div key={r} className="flex border-t border-border/50">
              <div className="w-[120px] h-10 shrink-0 border-r border-border flex items-center px-2">
                <div className="h-3 w-20 bg-muted/60 animate-pulse rounded" />
              </div>
              {Array.from({ length: 8 }).map((_, c) => (
                <div key={c} className="w-[68px] h-10 shrink-0 flex items-center justify-center">
                  <div className="h-5 w-10 bg-muted/40 animate-pulse rounded" />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="h-4 w-36 bg-muted animate-pulse rounded" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-[52px] bg-muted/30 animate-pulse rounded-md border border-border/30"
          />
        ))}
      </div>
    </div>
  );
}
