interface ScoreBadgeProps {
  score: number | null;
}

export default function ScoreBadge({ score }: ScoreBadgeProps) {
  if (score === null || score === undefined) {
    return <span className="inline-flex rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600">N/A</span>;
  }

  let colors: string;
  if (score > 70) {
    colors = "bg-green-100 text-green-800";
  } else if (score >= 40) {
    colors = "bg-yellow-100 text-yellow-800";
  } else {
    colors = "bg-red-100 text-red-800";
  }

  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${colors}`}>{score}</span>;
}
