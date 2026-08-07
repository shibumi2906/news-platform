"use client";
export default function AdminError({ reset }: { error: Error; reset: () => void }) { return <section className="admin-panel" role="alert"><p className="kicker">API unavailable</p><h1>Admin data could not be loaded</h1><p>The action was not retried automatically.</p><button onClick={reset}>Try again</button></section>; }
