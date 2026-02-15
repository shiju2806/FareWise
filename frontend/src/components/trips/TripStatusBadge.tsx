const statusStyles: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  searching: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  submitted: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  approved: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  rejected: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  changes_requested: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
};

interface Props {
  status: string;
  className?: string;
}

export function TripStatusBadge({ status, className = "" }: Props) {
  const style = statusStyles[status] || "bg-gray-100 text-gray-700";
  const label = status.replace(/_/g, " ");

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize ${style} ${className}`}
    >
      {label}
    </span>
  );
}
