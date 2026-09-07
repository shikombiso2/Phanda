import type { ErrorEnvelope } from "../types/api";

/** The one exception type every API call throws. Every failing endpoint --
 * 401, 404, 405, 422, 500 -- uses the same {code, message, details}
 * envelope, so this is the only error-shaped thing calling code needs to
 * know about. */
export class ApiError extends Error {
  readonly status: number;
  readonly envelope: ErrorEnvelope | null;

  constructor(status: number, envelope: ErrorEnvelope | null, cause?: unknown) {
    super(envelope?.message ?? `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.envelope = envelope;
    this.cause = cause;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** Safe to show a user as-is. */
  get displayMessage(): string {
    if (this.envelope) return this.envelope.message;
    if (this.status === 0) return "Can't reach Phanda right now. Check your connection and try again.";
    return `Something went wrong (${this.status}). Try again.`;
  }

  static network(cause: unknown): ApiError {
    return new ApiError(0, null, cause);
  }
}
