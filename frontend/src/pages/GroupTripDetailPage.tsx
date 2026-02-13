import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useCollaborationStore } from "@/stores/collaborationStore";
import { GroupTripDetailView } from "@/components/collaboration/GroupTripDetail";
import { Button } from "@/components/ui/button";

export default function GroupTripDetailPage() {
  const { groupId } = useParams<{ groupId: string }>();
  const navigate = useNavigate();
  const { groupDetail, loading, fetchGroupDetail } = useCollaborationStore();

  useEffect(() => {
    if (groupId) {
      fetchGroupDetail(groupId);
    }
  }, [groupId, fetchGroupDetail]);

  if (loading && !groupDetail) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-48 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  if (!groupDetail) {
    return (
      <div className="text-center py-12">
        <p className="text-lg font-medium">Group trip not found</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button
        variant="outline"
        size="sm"
        onClick={() => navigate("/group-trips")}
      >
        &larr; Back to Group Trips
      </Button>

      <GroupTripDetailView detail={groupDetail} />
    </div>
  );
}
