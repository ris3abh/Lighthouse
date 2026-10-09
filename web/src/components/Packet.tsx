import { Download, PackageCheck } from "lucide-react";
import { api, type PacketBuild } from "../api";
import { useLoad, useOnce } from "../hooks";
import { Button, ButtonLink, Card, Empty, plural, useToast } from "./ui";

const LABEL = "Draft for attorney review";

const FILES: [string, string][] = [
  ["packet.pdf", "Review PDF"],
  ["packet.docx", "Editable .docx"],
  ["attorney-export.zip", "Attorney export (ZIP)"],
  ["matrix.csv", "Matrix (CSV)"],
];

/** The review packet (ADR 0020): the case organized for an attorney to review. Never a petition; every page and every
 * generated paragraph is labeled. Same inputs, same files. */
export default function PacketPanel({ version }: { version: number }) {
  const toast = useToast();
  const list = useLoad(() => api.packets(), [version]);
  const { run, busy } = useOnce();
  const build = () =>
    run("packet", async () => {
      try {
        const m = await api.buildPacket();
        toast(`Built: ${plural(m.pages, "page")}, ${plural(m.exhibits.length, "exhibit")}. ${LABEL}.`);
        list.reload();
      } catch (e) {
        toast((e as Error).message, "error");
      }
    });
  const latest: PacketBuild | undefined = list.data?.[0];
  return (
    <Card
      title="Review packet"
      className="mb-8"
      panel="packet"
      actions={
        <Button size="sm" variant="primary" onClick={build} disabled={busy("packet")}>
          <PackageCheck /> {busy("packet") ? "Building…" : "Build review packet"}
        </Button>
      }
    >
      {!latest ? (
        <Empty>
          Numbered exhibits by criterion, an index with page ranges, every approved claim matched to the page its quote is on, an outline drafted from approved claims
          only, the open preflight issues and final merits. A .docx, a PDF and a ZIP for your attorney, every page labeled “{LABEL}”.
        </Empty>
      ) : (
        <div className="px-5 py-4">
          <p className="text-[15px]">
            {latest.name}: {plural(latest.pages, "page")}, {plural(latest.exhibits.length, "numbered exhibit")}, {plural(latest.claims, "cited claim")},{" "}
            {plural(latest.open_issues, "open preflight issue")}.
          </p>
          <p className="mt-1 font-mono text-[11px] break-all text-muted">
            {LABEL} · as of {latest.as_of.slice(0, 10)} · input {latest.input_hash.slice(0, 16)}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {FILES.filter(([f]) => latest.files_present.includes(f)).map(([f, label]) => (
              <ButtonLink key={f} size="sm" href={`/api/packets/${encodeURIComponent(latest.name)}/${f}`} download>
                <Download /> {label}
              </ButtonLink>
            ))}
          </div>
          {list.data && list.data.length > 1 && <p className="mt-3 text-xs text-ink-2">{plural(list.data.length - 1, "earlier build")} kept in exports/.</p>}
        </div>
      )}
    </Card>
  );
}
