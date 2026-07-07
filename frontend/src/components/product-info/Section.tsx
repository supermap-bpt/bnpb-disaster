import { ChevronDown } from "lucide-react";

function Section({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details className="group border-b last:border-b-0" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center justify-between py-2 text-sm font-semibold">
        {title}
        <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className="pb-3">{children}</div>
    </details>
  );
}

export default Section;
