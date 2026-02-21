export interface TripOverlap {
  id: string;
  overlap_city: string;
  overlap_start: string;
  overlap_end: string;
  overlap_days: number;
  dismissed: boolean;
  other_trip: {
    id: string;
    title: string;
    traveler: string;
    department: string | null;
  };
}
