import Image from "next/image";

// Use the same local employer assets as the landing page: no third-party
// network request, layout shift or broken external logo URL on the dashboard.
const EMPLOYER_ASSETS: ReadonlyArray<[RegExp, string]> = [
  [/\badvanced micro devices\b|\bamd\b/i, "amd"],
  [/\bnvidia\b/i, "nvidia"],
  [/\bamazon\b|\baws\b/i, "amazon"],
  [/\bibm\b|international business machines/i, "ibm"],
];

export function companyLogoAsset(company: string): string | null {
  return EMPLOYER_ASSETS.find(([pattern]) => pattern.test(company))?.[1] ?? null;
}

export function CompanyLogo({ company, size = "medium" }: { company: string; size?: "small" | "medium" | "large" }) {
  const asset = companyLogoAsset(company);
  const initials = company.trim().split(/\s+/).slice(0, 2).map((word) => word[0] ?? "").join("").toUpperCase() || "?";
  return (
    <span className={`company-logo company-logo--${size}${asset ? ` company-logo--${asset}` : " company-logo--fallback"}`} aria-label={`${company} logo`}>
      {asset ? <Image src={`/brand-icons/${asset}.svg`} alt="" width={64} height={48} unoptimized />
        : <span aria-hidden="true">{initials}</span>}
    </span>
  );
}
