import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { cx } from "./ui";

const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");

/** A file's path inside a dropped folder ("export/conversations/2026-08-01.json"), else its name. */
export function filePath(f: File): string {
  return (f as File & { lhPath?: string }).lhPath || f.webkitRelativePath || f.name;
}

/** Everything dropped, with folders walked (Chrome, Safari and Firefox expose dropped folders as entries). */
async function droppedFiles(e: DragEvent): Promise<File[]> {
  const entries: FileSystemEntry[] = [];
  for (const it of Array.from(e.dataTransfer.items ?? [])) {
    const entry = it.webkitGetAsEntry?.();
    if (entry) entries.push(entry);
  }
  if (!entries.some((x) => x.isDirectory)) return Array.from(e.dataTransfer.files);
  const out: File[] = [];
  const walk = async (entry: FileSystemEntry): Promise<void> => {
    if (entry.isFile) {
      const f = await new Promise<File>((ok, err) => (entry as FileSystemFileEntry).file(ok, err));
      Object.defineProperty(f, "lhPath", { value: entry.fullPath.replace(/^\//, "") });
      out.push(f);
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      for (;;) {
        const batch = await new Promise<FileSystemEntry[]>((ok, err) => reader.readEntries(ok, err));
        if (!batch.length) break;
        for (const child of batch) await walk(child);
      }
    }
  };
  for (const entry of entries) await walk(entry);
  return out;
}

/** Props to make any element a file drop target; `over` is true while files hover it. */
export function useFileDrop(onFiles: (files: File[]) => void) {
  const [over, setOver] = useState(false);
  const depth = useRef(0); // dragenter/leave fire for every child; count them
  const bind = {
    onDragEnter: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current += 1;
      setOver(true);
    },
    onDragOver: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    },
    onDragLeave: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setOver(false);
    },
    onDrop: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.stopPropagation(); // a criterion card handles its own drop; the page zone doesn't also fire
      depth.current = 0;
      setOver(false);
      droppedFiles(e).then((files) => files.length && onFiles(files), () => onFiles(Array.from(e.dataTransfer.files)));
    },
  };
  return { over, bind };
}

/** The big "drop files here" bar with a click-to-choose fallback (keyboard accessible). */
export default function DropZone({
  onFiles,
  busy,
  children,
  accept,
  multiple,
  label = "Upload files to the Inbox",
}: {
  onFiles: (files: File[]) => void;
  busy?: boolean;
  children: ReactNode;
  accept?: string;
  multiple?: boolean;
  label?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const { over, bind } = useFileDrop(onFiles);
  return (
    <div
      {...bind}
      role="button"
      tabIndex={0}
      aria-label={label}
      onClick={() => input.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), input.current?.click())}
      className={cx(
        "mb-8 flex cursor-pointer flex-col items-center justify-center gap-2 border border-dashed px-6 py-10 text-center transition-colors duration-150",
        over ? "border-ink bg-sunken" : "border-ink-2 hover:border-ink hover:bg-surface",
        busy && "pointer-events-none opacity-60",
      )}
    >
      {children}
      <input
        ref={input}
        type="file"
        multiple={multiple ?? !accept}
        accept={accept}
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) onFiles(files);
        }}
      />
    </div>
  );
}
