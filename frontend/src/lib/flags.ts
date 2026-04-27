export const FLAG_NAMES = [
  "lens_clear",
  "lens_cracked",
  "housing_cracked",
  "tabs_intact",
  "moisture_inside",
  "all_bulbs_working",
  "tested",
  "oem",
  "complete_assembly",
] as const;

export type FlagName = (typeof FLAG_NAMES)[number];

export type FlagDict = Partial<Record<FlagName, boolean | null>>;

export const HARD_FILTER_FLAGS: ReadonlySet<FlagName> = new Set([
  "lens_cracked",
  "housing_cracked",
  "complete_assembly",
]);

// User-facing label + a help string explaining what TRUE means.
export const FLAG_LABELS: Record<FlagName, { label: string; trueMeans: string }> = {
  lens_clear:        { label: "Lens is clear",            trueMeans: "Not yellowed/hazed/oxidized." },
  lens_cracked:      { label: "Lens is cracked",          trueMeans: "Visible crack, hole, or chip in the lens." },
  housing_cracked:   { label: "Housing is cracked",       trueMeans: "The plastic shell/case has a crack." },
  tabs_intact:       { label: "Mounting tabs intact",     trueMeans: "All tabs present and unbroken." },
  moisture_inside:   { label: "Moisture inside",          trueMeans: "Condensation or water inside the assembly." },
  all_bulbs_working: { label: "All bulbs working",        trueMeans: "Tested — every bulb/beam fires." },
  tested:            { label: "Tested by seller",         trueMeans: "Seller bench-tested it (vs. as-is)." },
  oem:               { label: "OEM / factory original",   trueMeans: "Genuine factory part, not aftermarket." },
  complete_assembly: { label: "Complete assembly",        trueMeans: "Whole assembly, not lens/housing/bulb only." },
};
