import Banter from "../components/Banter";
import { Button } from "../components/ui";

/** An address that isn't a page (the only error that gets banter, ADR 0010 §4). */
export default function NotFound() {
  return (
    <div className="mx-auto max-w-2xl py-16 text-center">
      <h1 className="sr-only">Page not found</h1>
      <p className="eyebrow">404</p>
      <Banter id="not_found" className="display mt-4 text-5xl md:text-7xl" fallback="This page doesn't exist." />
      <p className="mt-5 text-[15px] text-ink-2">The address doesn't match any page here.</p>
      <Button className="mt-8" variant="primary" onClick={() => (window.location.hash = "#/overview")}>
        Back to the Overview
      </Button>
    </div>
  );
}
