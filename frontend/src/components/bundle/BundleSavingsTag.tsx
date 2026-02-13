interface Props {
  savings: number;
}

export function BundleSavingsTag({ savings }: Props) {
  if (savings <= 0) return null;

  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 rounded">
      Save ${Math.round(savings)}
    </span>
  );
}
