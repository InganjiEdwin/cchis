"use client";

import { ShieldCheck, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBanner } from "@/components/ui/status-banner";
import { verifyStepUpViaBff, type StepUpPurpose } from "@/lib/auth";
import { registerStepUpHandler, StepUpCancelledError } from "@/lib/step-up";

type StepUpRequest = {
  id: number;
  purpose: StepUpPurpose;
  resolve: () => void;
  reject: (error: Error) => void;
};

let nextRequestId = 1;

export function StepUpDialogProvider({ children }: { children: React.ReactNode }) {
  const queueRef = useRef<StepUpRequest[]>([]);
  const activeRequestRef = useRef<StepUpRequest | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [activeRequest, setActiveRequest] = useState<StepUpRequest | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);

  const openNextRequest = useCallback(() => {
    if (activeRequestRef.current) {
      return;
    }

    const nextRequest = queueRef.current.shift() ?? null;
    activeRequestRef.current = nextRequest;
    setActiveRequest(nextRequest);
    setCode("");
    setError(null);
    setIsVerifying(false);
  }, []);

  const settleRequest = useCallback((request: StepUpRequest, errorToReject?: Error) => {
    if (errorToReject) {
      request.reject(errorToReject);
    } else {
      request.resolve();
    }

    activeRequestRef.current = null;
    setActiveRequest(null);
    setCode("");
    setError(null);
    setIsVerifying(false);
    window.setTimeout(openNextRequest, 0);
  }, [openNextRequest]);

  useEffect(() => {
    const unregister = registerStepUpHandler((purpose) => (
      new Promise<void>((resolve, reject) => {
        queueRef.current.push({
          id: nextRequestId,
          purpose,
          resolve,
          reject,
        });
        nextRequestId += 1;
        openNextRequest();
      })
    ));

    return () => {
      unregister();
      const cancelError = new StepUpCancelledError();
      activeRequestRef.current?.reject(cancelError);
      queueRef.current.splice(0).forEach((request) => request.reject(cancelError));
      activeRequestRef.current = null;
    };
  }, [openNextRequest]);

  useEffect(() => {
    if (!activeRequest) {
      return;
    }

    inputRef.current?.focus();
  }, [activeRequest]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!activeRequest || code.length !== 6 || isVerifying) {
      return;
    }

    setIsVerifying(true);
    setError(null);

    try {
      await verifyStepUpViaBff(code, activeRequest.purpose);
      settleRequest(activeRequest);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to confirm this action.");
      setIsVerifying(false);
    }
  }

  function handleCancel() {
    if (!activeRequest || isVerifying) {
      return;
    }

    settleRequest(activeRequest, new StepUpCancelledError());
  }

  return (
    <>
      {children}
      {activeRequest ? (
        <div className="fixed inset-0 z-[100000] flex items-center justify-center bg-[color-mix(in_srgb,#020617_78%,transparent)] px-4 py-6 backdrop-blur-sm">
          <Card
            className="w-full max-w-md px-6 py-6 shadow-[0_28px_80px_rgba(0,0,0,0.35)]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-identity-title"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <span className="inline-flex size-10 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,transparent)] text-brand">
                  <ShieldCheck className="size-5" aria-hidden="true" />
                </span>
                <h2 id="confirm-identity-title" className="mt-4 text-xl font-semibold text-panel-strong">
                  Confirm it is you
                </h2>
                <p className="mt-2 text-sm leading-6 text-panel-muted">
                  This action needs a quick security check. Enter your authenticator code to continue.
                </p>
              </div>
              <button
                type="button"
                onClick={handleCancel}
                disabled={isVerifying}
                className="inline-flex size-10 shrink-0 items-center justify-center rounded-full text-panel-muted transition hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_42%,transparent)] hover:text-panel-strong disabled:pointer-events-none disabled:opacity-60"
                aria-label="Cancel confirmation"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>

            {error ? <StatusBanner tone="danger" className="mt-5">{error}</StatusBanner> : null}

            <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
              <label className="block">
                <span className="text-sm font-semibold text-panel-copy">6-digit code</span>
                <input
                  ref={inputRef}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  maxLength={6}
                  value={code}
                  onChange={(event) => {
                    setCode(event.target.value.replace(/\D/g, "").slice(0, 6));
                    if (error) {
                      setError(null);
                    }
                  }}
                  className="mt-2 h-12 w-full rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-center text-lg font-semibold text-panel-strong outline-none focus:border-brand"
                  required
                />
              </label>

              <div className="flex flex-wrap justify-end gap-3 pt-2">
                <Button type="button" variant="secondary" onClick={handleCancel} disabled={isVerifying}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isVerifying || code.length !== 6}>
                  {isVerifying ? "Confirming..." : "Confirm"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      ) : null}
    </>
  );
}
