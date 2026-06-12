interface SystemBadgeProps {
  name: string;
  os: string | null;
  className?: string;
}

interface ColorSet { bg: string; text: string; border: string }

// Vibrant palette — every system gets a color. The same name always maps to the same color.
const PALETTE: ColorSet[] = [
  { bg: "bg-blue-500/15", text: "text-blue-300", border: "border-blue-500/20" },
  { bg: "bg-emerald-500/15", text: "text-emerald-300", border: "border-emerald-500/20" },
  { bg: "bg-[rgba(234,88,12,0.15)]", text: "text-[#fdba74]", border: "border-orange-500/20" },
  { bg: "bg-indigo-500/15", text: "text-indigo-300", border: "border-indigo-500/20" },
  { bg: "bg-cyan-500/15", text: "text-cyan-300", border: "border-cyan-500/20" },
  { bg: "bg-rose-500/15", text: "text-rose-300", border: "border-rose-500/20" },
  { bg: "bg-amber-500/15", text: "text-amber-300", border: "border-amber-500/20" },
  { bg: "bg-teal-500/15", text: "text-teal-300", border: "border-teal-500/20" },
  { bg: "bg-fuchsia-500/15", text: "text-fuchsia-300", border: "border-fuchsia-500/20" },
  { bg: "bg-sky-500/15", text: "text-sky-300", border: "border-sky-500/20" },
];

// DataCard-compatible edge colors, mapped 1:1 with the PALETTE indices above.
// DataCard only supports: purple, blue, cyan, green, orange, pink, red
// We map the 10 palette entries to the closest DataCard color.
const EDGE_COLOR_PALETTE = [
  "blue",    // 0: blue
  "green",   // 1: emerald → green
  "orange",  // 2: orange
  "blue",    // 3: indigo → blue (purple reserved for selection)
  "cyan",    // 4: cyan
  "pink",    // 5: rose → pink
  "orange",  // 6: amber → orange
  "cyan",    // 7: teal → cyan
  "pink",    // 8: fuchsia → pink
  "blue",    // 9: sky → blue
] as const;

export type DataCardEdgeColor = "purple" | "blue" | "cyan" | "green" | "orange" | "pink" | "red";

function hashName(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function resolveColor(name: string): ColorSet {
  return PALETTE[hashName(name) % PALETTE.length];
}

/** Returns a DataCard-compatible edgeColor for a given system name. */
export function resolveEdgeColor(systemName: string): DataCardEdgeColor {
  return EDGE_COLOR_PALETTE[hashName(systemName) % EDGE_COLOR_PALETTE.length];
}

export function SystemBadge({ name, className = "" }: SystemBadgeProps) {
  const colors = resolveColor(name);

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs border ${colors.bg} ${colors.text} ${colors.border} ${className}`}
    >
      {name}
    </span>
  );
}
