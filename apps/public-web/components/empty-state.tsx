export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <section className="empty-state" role="status">
      <h2>{title}</h2>
      <p>{detail}</p>
    </section>
  );
}
