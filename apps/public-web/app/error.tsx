"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <section className="empty-state" role="alert"><p className="kicker">Connection problem</p><h1>The newsroom is temporarily unavailable</h1><p>No unpublished content or technical details were exposed.</p><button type="button" onClick={reset}>Try again</button></section>;
}
