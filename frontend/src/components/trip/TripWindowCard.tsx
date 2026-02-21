/**
 * Trip-window proposal card — shows date shift alternatives.
 * Shared between TripReview (traveler) and ApprovalDetailPage (manager).
 */

import { formatPrice } from "@/lib/currency";
import { formatShortDate } from "@/lib/dates";
import type { TripWindowProposal } from "@/types/search";

export function TripWindowCard({ proposal }: { proposal: TripWindowProposal }) {
  return (
    <div className="rounded-md border border-blue-100 bg-blue-50/30 px-3 py-2.5 space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs">
          <span className="font-medium">{formatShortDate(proposal.outbound_date)}</span>
          <span className="text-muted-foreground">&rarr;</span>
          <span className="font-medium">{formatShortDate(proposal.return_date)}</span>
          <span className="text-[10px] text-muted-foreground ml-1">
            ({proposal.trip_duration}d)
          </span>
          {proposal.airline_name && (
            <span className={`text-[9px] rounded-full px-1.5 py-0.5 ${
              proposal.user_airline
                ? "bg-primary/10 text-primary font-medium"
                : "bg-blue-100 text-blue-700"
            }`}>
              {proposal.user_airline ? `\u2713 ${proposal.airline_name}` : proposal.airline_name}
            </span>
          )}
        </div>
        <div className="text-right">
          <span className="text-sm font-bold">{formatPrice(proposal.total_price)}</span>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div className="text-[10px] text-muted-foreground flex gap-2">
          <span>
            Out: {proposal.outbound_flight.airline_name} {formatPrice(proposal.outbound_flight.price)}
          </span>
          <span>
            Ret: {proposal.return_flight.airline_name} {formatPrice(proposal.return_flight.price)}
          </span>
        </div>
        <span className={`text-[10px] font-semibold ${
          proposal.savings >= 0 ? "text-blue-700" : "text-amber-600"
        }`}>
          {proposal.savings >= 0
            ? `Save ${formatPrice(proposal.savings)}`
            : `${formatPrice(Math.abs(proposal.savings))} more`
          }
        </span>
      </div>
      {proposal.reason && (
        <p className="text-[10px] text-muted-foreground italic">{proposal.reason}</p>
      )}
    </div>
  );
}
