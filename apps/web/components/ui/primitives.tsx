"use client";
import { useEffect, useRef, type ReactNode } from "react";
import { ApiError, errorMessage } from "@/lib/api/client";
import { trustInfo, humanize } from "@/lib/format";
import type { TrustStatus } from "@/lib/api/types";
export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    ask: (
      <>
        <path d="M4 4h16v12H9l-5 4z" />
        <path d="M8 8h8M8 12h5" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="1" />
        <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
      </>
    ),
    runs: (
      <>
        <path d="m9 5 10 7-10 7z" />
        <path d="M4 4v16" />
      </>
    ),
    review: (
      <>
        <path d="m12 3 9 4v5c0 5-9 9-9 9S3 17 3 12V7z" />
        <path d="M12 8v5m0 3v1" />
      </>
    ),
    history: (
      <>
        <path d="M3 11a9 9 0 1 1 2 7M3 4v7h7" />
        <path d="M12 7v5l4 2" />
      </>
    ),
    arrow: (
      <>
        <path d="M4 12h15m-6-6 6 6-6 6" />
      </>
    ),
    close: <path d="m6 6 12 12M6 18 18 6" />,
    search: (
      <>
        <circle cx="10" cy="10" r="6" />
        <path d="m15 15 5 5" />
      </>
    ),
    download: (
      <>
        <path d="M12 3v12m-5-5 5 5 5-5M4 15v5h16v-5" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    proof: (
      <>
        <path d="M5 3h11l3 3v15H5zM15 3v5h4M8 12h8M8 16h5" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.proof}
    </svg>
  );
}
export function TrustBadge({
  status,
  compact = false,
}: {
  status: TrustStatus;
  compact?: boolean;
}) {
  const info = trustInfo[status] || trustInfo.NEEDS_REVIEW;
  return (
    <span
      className={`trust trust-${status.toLowerCase().replaceAll("_", "-")} ${compact ? "trust-compact" : ""}`}
      title={info.description}
    >
      <span aria-hidden="true" className="trust-symbol">
        {info.symbol}
      </span>
      <span>{info.label}</span>
    </span>
  );
}
export function Status({ value }: { value: string }) {
  return (
    <span className={`status status-${value.toLowerCase()}`}>
      <span aria-hidden="true">
        {["COMPLETED", "SUCCEEDED", "FINALIZED"].includes(value)
          ? "✓"
          : ["FAILED", "PARTIAL"].includes(value)
            ? "!"
            : "○"}
      </span>{" "}
      {humanize(value)}
    </span>
  );
}
export function ErrorNotice({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <strong>Something needs attention</strong>
      <p>{errorMessage(error)}</p>
      {error instanceof ApiError && (
        <small className="mono">
          {error.code}
          {error.correlationId ? ` · Reference ${error.correlationId}` : ""}
        </small>
      )}
      {retry && (
        <button className="button secondary" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
export function Loading({ label = "Loading workspace…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="loading-mark" aria-hidden="true" />
      <span>{label}</span>
      <div className="skeleton" />
      <div className="skeleton short" />
    </div>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Icon name="grid" size={30} />
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Pager({
  offset,
  limit,
  total,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
}) {
  return (
    <div className="pager">
      <span className="mono">
        {total
          ? `${offset + 1}–${Math.min(offset + limit, total)} of ${total}`
          : "0 results"}
      </span>
      <div className="actions">
        <button
          className="button small secondary"
          disabled={!offset}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button
          className="button small secondary"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  drawer = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  drawer?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={drawer ? "drawer" : "modal"}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) {
          const rect = ref.current.getBoundingClientRect();
          if (
            e.clientX < rect.left ||
            e.clientX > rect.right ||
            e.clientY < rect.top ||
            e.clientY > rect.bottom
          )
            onClose();
        }
      }}
    >
      <div className="dialog-head">
        <div>
          <span className="eyebrow">ProofGrid / inspection</span>
          <h2>{title}</h2>
        </div>
        <button
          className="icon-button"
          autoFocus
          onClick={onClose}
          aria-label="Close dialog"
        >
          <Icon name="close" />
        </button>
      </div>
      <div className="dialog-body">{children}</div>
    </dialog>
  );
}
