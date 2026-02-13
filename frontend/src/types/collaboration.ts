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

export interface GroupTripSummary {
  id: string;
  name: string;
  destination_city: string;
  start_date: string;
  end_date: string;
  status: string;
  notes: string | null;
  my_role: string;
  my_status: string;
  organizer: string;
  member_count: number;
  accepted_count: number;
}

export interface GroupTripMember {
  id: string;
  user_id: string;
  name: string;
  email: string;
  department: string | null;
  role: string;
  status: string;
  trip_id: string | null;
}

export interface GroupTripDetail {
  id: string;
  name: string;
  destination_city: string;
  start_date: string;
  end_date: string;
  status: string;
  notes: string | null;
  organizer: string;
  members: GroupTripMember[];
  coordination_tips: string[];
}
