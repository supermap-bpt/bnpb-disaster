function AttributeTable({ rows }: { rows: { label: string; value: string }[] }) {
  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground">—</p>;
  }
  return (
    <dl className="grid grid-cols-[150px_1fr] gap-x-4 gap-y-3 text-sm">
      {rows.map(({ label, value }) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="break-all font-medium">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export default AttributeTable;
