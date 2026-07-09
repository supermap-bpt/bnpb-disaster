import { useState, type ReactNode } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm, useWatch } from "react-hook-form";
import { CalendarIcon, ChevronDown, Cloud } from "lucide-react";
import { format, parseISO } from "date-fns";
import { filterSchema, type FilterFormValues } from "../schemas/filterSchema";
import { useGIS, INDONESIA_BBOX } from "../context/GISContext";
import { fetchSearch } from "../api/client";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { useLanguage } from "@/context/LanguageContext";

const CALENDAR_START_MONTH = new Date(2014, 3, 1);
const CALENDAR_END_MONTH = new Date(new Date().getFullYear() + 1, 11, 1);

const SATELLITE_GROUPS = [
  {
    id: "sentinel-1",
    label: "Sentinel-1",
    sensorId: "c-sar",
    sensorLabel: "C-SAR",
    leaves: [
      { value: "SENTINEL_1_SLC", label: "Level 1-SLC" },
      { value: "SENTINEL_1_GRD", label: "Level 1-GRD" },
    ],
  },
  {
    id: "sentinel-2",
    label: "Sentinel-2",
    sensorId: "msi",
    sensorLabel: "MSI",
    leaves: [
      { value: "SENTINEL_2_L1C", label: "L1C" },
      { value: "SENTINEL_2_L2A", label: "L2A" },
    ],
  },
  {
    id: "sentinel-3",
    label: "Sentinel-3",
    sensorId: "slstr",
    sensorLabel: "SLSTR",
    leaves: [
      { value: "SENTINEL_3_SLSTR_L2_LST", label: "Level-2 LST" },
      { value: "SENTINEL_3_SLSTR_L2_WST", label: "Level-2 WST" },
    ],
  },
] as const;

const ALL_LEAF_VALUES = SATELLITE_GROUPS.flatMap((group) => group.leaves.map((leaf) => leaf.value));

export function DateField({
  id,
  label,
  placeholder,
  value,
  onChange,
}: {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-1 flex-col gap-1">
      <label className="text-sm font-medium" htmlFor={id}>
        {label}
      </label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            id={id}
            type="button"
            variant="outline"
            className={cn("justify-start text-left font-normal", !value && "text-muted-foreground")}
          >
            <CalendarIcon className="mr-2 h-4 w-4" />
            {value ? format(parseISO(value), "d MMM yyyy") : placeholder}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="single"
            captionLayout="dropdown"
            startMonth={CALENDAR_START_MONTH}
            endMonth={CALENDAR_END_MONTH}
            selected={value ? parseISO(value) : undefined}
            onSelect={(date) => {
              if (!date) return;
              onChange(format(date, "yyyy-MM-dd"));
              setOpen(false);
            }}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}

const DEFAULT_FORM_VALUES: FilterFormValues = { productType: ["SENTINEL_1_GRD"], cloudCoverMax: 100, dateFrom: "", dateUntil: "" };

function TreeNode({
  id,
  label,
  checked,
  onCheckedChange,
  open,
  onToggleOpen,
  children,
}: {
  id: string;
  label: string;
  checked: boolean | "indeterminate";
  onCheckedChange: (checked: boolean | "indeterminate") => void;
  open: boolean;
  onToggleOpen: () => void;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-sm font-medium">
        <button
          type="button"
          aria-label={open ? `Collapse ${label}` : `Expand ${label}`}
          onClick={onToggleOpen}
          className="rounded p-0.5 hover:bg-muted"
        >
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", !open && "-rotate-90")} />
        </button>
        <Checkbox id={id} checked={checked} onCheckedChange={onCheckedChange} />
        <label htmlFor={id}>{label}</label>
      </div>
      {open && <div className="ml-5 flex flex-col gap-1">{children}</div>}
    </div>
  );
}

function FilterPanel() {
  const {
    placeRing,
    addressQuery,
    setPlaceRing,
    setSearchResults,
    setLastSearchFilter,
    isSearching,
    setIsSearching,
    error,
    setError,
    resetAll,
  } = useGIS();
  const { t } = useLanguage();
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FilterFormValues>({
    resolver: zodResolver(filterSchema),
    defaultValues: DEFAULT_FORM_VALUES,
  });
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const isGroupOpen = (id: string) => openGroups[id] ?? true;
  const toggleGroupOpen = (id: string) =>
    setOpenGroups((prev) => ({ ...prev, [id]: !isGroupOpen(id) }));
  const productTypeWatch = useWatch({ control, name: "productType" });
  const hasSentinel2Checked = (productTypeWatch ?? []).some((value) => value.startsWith("SENTINEL_2"));

  const onSubmit = async (values: FilterFormValues) => {
    const aoiRing = addressQuery.trim() === "" ? INDONESIA_BBOX : placeRing;
    if (aoiRing === null) {
      setError(t("noAoiError"));
      return;
    }
    setError(null);
    setIsSearching(true);
    try {
      const { results, total } = await fetchSearch(values, aoiRing, 0);
      setPlaceRing(aoiRing);
      setLastSearchFilter(values);
      setSearchResults(results, total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("searchFailed"));
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3 rounded-lg bg-card/60 p-3">
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-medium">
          {t("dataSource")}
        </legend>
        <Controller
          control={control}
          name="productType"
          render={({ field }) => (
            <>
              {SATELLITE_GROUPS.map((group) => {
                const leafValues = group.leaves.map((leaf) => leaf.value);
                const checkedCount = leafValues.filter((v) => field.value?.includes(v)).length;
                const groupState: boolean | "indeterminate" =
                  checkedCount === 0 ? false : checkedCount === leafValues.length ? true : "indeterminate";
                const setGroupAll = (checked: boolean | "indeterminate") => {
                  const current = field.value ?? [];
                  const withoutGroup = current.filter((v) => !leafValues.includes(v));
                  field.onChange(checked === true ? [...withoutGroup, ...leafValues] : withoutGroup);
                };

                return (
                  <TreeNode
                    key={group.id}
                    id={group.id}
                    label={group.label}
                    checked={groupState}
                    onCheckedChange={setGroupAll}
                    open={isGroupOpen(group.id)}
                    onToggleOpen={() => toggleGroupOpen(group.id)}
                  >
                    <TreeNode
                      id={group.sensorId}
                      label={group.sensorLabel}
                      checked={groupState}
                      onCheckedChange={setGroupAll}
                      open={isGroupOpen(group.sensorId)}
                      onToggleOpen={() => toggleGroupOpen(group.sensorId)}
                    >
                      {group.leaves.map(({ value, label }) => {
                        const checked = field.value?.includes(value) ?? false;
                        return (
                          <label key={value} htmlFor={value} className="flex items-center gap-2 text-sm">
                            <Checkbox
                              id={value}
                              checked={checked}
                              onCheckedChange={(next) => {
                                const current = field.value ?? [];
                                const updated = next
                                  ? [...current, value]
                                  : current.filter((item) => item !== value);
                                field.onChange(ALL_LEAF_VALUES.filter((v) => updated.includes(v)));
                              }}
                            />
                            {label}
                          </label>
                        );
                      })}
                    </TreeNode>
                  </TreeNode>
                );
              })}
            </>
          )}
        />
        <Controller
          control={control}
          name="cloudCoverMax"
          render={({ field }) => (
            <div className="flex items-center gap-2 pl-5">
              <Cloud className="h-4 w-4 shrink-0 text-muted-foreground" />
              <Slider
                min={0}
                max={100}
                step={1}
                value={[field.value]}
                onValueChange={([next]) => field.onChange(next)}
                disabled={!hasSentinel2Checked}
                className="flex-1"
              />
              <span className="w-9 shrink-0 text-right text-xs text-muted-foreground">{field.value}%</span>
            </div>
          )}
        />
      </fieldset>
      {errors.productType && (
        <p className="text-xs text-destructive">{errors.productType.message}</p>
      )}

      <div className="flex gap-2">
        <Controller
          control={control}
          name="dateFrom"
          render={({ field }) => (
            <DateField
              id="dateFrom"
              label={t("dateFrom")}
              placeholder={t("pickDate")}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
        <Controller
          control={control}
          name="dateUntil"
          render={({ field }) => (
            <DateField
              id="dateUntil"
              label={t("dateUntil")}
              placeholder={t("pickDate")}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
      </div>
      {errors.dateFrom && <p className="text-xs text-destructive">{errors.dateFrom.message}</p>}
      {errors.dateUntil && <p className="text-xs text-destructive">{errors.dateUntil.message}</p>}

      <Button type="submit" disabled={isSearching} className="w-full">
        {isSearching ? t("searching") : t("search")}
      </Button>

      <Button
        type="button"
        variant="outline"
        className={cn(
          "w-full transition-colors",
          // Light mode
          "border-blue-500 bg-white text-blue-600 hover:border-blue-600 hover:bg-blue-50",
          // Dark mode
          "dark:border-slate-500 dark:bg-card dark:text-slate-200",
          "dark:hover:border-slate-600 dark:hover:bg-slate-800",
          // Focus
          "focus-visible:ring-2 focus-visible:ring-blue-500"
        )}
        onClick={() => {
          resetAll();
          reset(DEFAULT_FORM_VALUES);
        }}
      >
        {t("resetMap")}
      </Button>

      {error && <p className="text-xs text-destructive">{error}</p>}
    </form>
  );
}

export default FilterPanel;
