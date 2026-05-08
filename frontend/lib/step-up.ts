import type { StepUpPurpose } from "@/lib/auth";

const STEP_UP_PURPOSES = new Set<string>([
  "admin_actions",
  "security_admin",
  "system_controls",
  "sensitive_exports",
  "sensitive_export_download",
  "source_data",
  "message_governance",
  "alert_delivery",
  "operational_data",
]);

type StepUpHandler = (purpose: StepUpPurpose) => Promise<void>;

let activeHandler: StepUpHandler | null = null;

export class StepUpUnavailableError extends Error {
  constructor() {
    super("Confirmation is required before this action can continue.");
    this.name = "StepUpUnavailableError";
  }
}

export class StepUpCancelledError extends Error {
  constructor() {
    super("Confirmation cancelled.");
    this.name = "StepUpCancelledError";
  }
}

export function isStepUpPurpose(value: string): value is StepUpPurpose {
  return STEP_UP_PURPOSES.has(value);
}

export function registerStepUpHandler(handler: StepUpHandler) {
  activeHandler = handler;

  return () => {
    if (activeHandler === handler) {
      activeHandler = null;
    }
  };
}

export function requestStepUp(purpose: StepUpPurpose) {
  if (!activeHandler) {
    return Promise.reject(new StepUpUnavailableError());
  }

  return activeHandler(purpose);
}
