import type {ApiClientError} from "../../../lib/api/client";

interface ErrorNoticeProps {
  error: ApiClientError | null;
  onRetry: () => void;
  actionLabel?: string;
}

export function ErrorNotice({error, onRetry, actionLabel = "Retry generation"}: ErrorNoticeProps) {
  if (!error) {
    return null;
  }
  return (
    <div className="notice" role="alert">
      <strong>{error.payload.error.code}</strong>
      <p>{error.payload.error.message}</p>
      <button className="button-secondary" onClick={onRetry}>{actionLabel}</button>
      <div className="notice-meta">HTTP {error.statusCode || "network"}</div>
    </div>
  );
}
