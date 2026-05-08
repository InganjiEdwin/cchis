"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Copy,
  Download,
  Edit3,
  Eye,
  EyeOff,
  Globe2,
  KeyRound,
  Laptop,
  LogOut,
  MapPinned,
  Monitor,
  MonitorCog,
  Moon,
  RefreshCw,
  ShieldCheck,
  ShieldAlert,
  Save,
  Sun,
  Trash2,
  UserRound,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PasswordPolicyChecklist } from "@/components/ui/password-policy-checklist";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  AuthStepUpRequiredError,
  changePasswordViaBff,
  fetchProfileActivityViaBff,
  fetchProfileSessionsViaBff,
  fetchRecoveryCodeStatusViaBff,
  isValidUsername,
  normalizeCurrentUser,
  regenerateRecoveryCodesViaBff,
  revokeAllProfileSessionsViaBff,
  revokeOtherProfileSessionsViaBff,
  revokeProfileSessionViaBff,
  verifyProfileIdentityTwoFactorViaBff,
  type CurrentUser,
  type ProfileActivityEvent,
  type ProfileActivityFilters,
  type ProfileSessionRecord,
  type ProfileSessionRevokeResponse,
  type ThemePreference,
} from "@/lib/auth";
import { generateStrongPassword, getPasswordPolicyError } from "@/lib/password-policy";
import { queryKeys } from "@/lib/query-keys";
import { requestStepUp } from "@/lib/step-up";

const appearanceOptions = [
  { value: "LIGHT", label: "Light", Icon: Sun },
  { value: "SYSTEM", label: "System", Icon: Monitor },
  { value: "DARK", label: "Dark", Icon: Moon },
] satisfies Array<{ value: ThemePreference; label: string; Icon: typeof Sun }>;

const activityEventOptions = [
  { value: "LOGIN_SUCCESS", label: "Login successful" },
  { value: "LOGIN_FAILED", label: "Login failed" },
  { value: "LOGOUT", label: "Signed out" },
  { value: "REFRESH_SUCCESS", label: "Session refreshed" },
  { value: "REFRESH_FAILED", label: "Session refresh failed" },
  { value: "PASSWORD_CHANGED", label: "Password changed" },
  { value: "PASSWORD_RESET_COMPLETED", label: "Password reset completed" },
  { value: "TWO_FACTOR_ENROLLMENT_REQUIRED", label: "2FA setup required" },
  { value: "TWO_FACTOR_ENROLLMENT_STARTED", label: "2FA setup started" },
  { value: "TWO_FACTOR_ENROLLMENT_COMPLETED", label: "2FA setup completed" },
  { value: "TWO_FACTOR_REQUIRED", label: "2FA required" },
  { value: "TWO_FACTOR_VERIFIED", label: "2FA verified" },
  { value: "TWO_FACTOR_FAILED", label: "2FA failed" },
  { value: "TWO_FACTOR_RECOVERY_CODES_GENERATED", label: "Recovery codes generated" },
  { value: "TWO_FACTOR_RECOVERY_CODES_REGENERATED", label: "Recovery codes regenerated" },
  { value: "TWO_FACTOR_RECOVERY_CODE_USED", label: "Recovery code used" },
  { value: "TWO_FACTOR_RECOVERY_CODE_FAILED", label: "Recovery code failed" },
  { value: "TWO_FACTOR_RECOVERY_CODES_LOW", label: "Recovery codes low" },
] satisfies Array<{ value: string; label: string }>;

function getInitials(name: string) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");

  return initials || "U";
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return "Not recorded";
  }

  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return "Not recorded";
  }

  return new Intl.DateTimeFormat("en-KE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function getScopeLabel(user: CurrentUser) {
  if (user.scope_type === "WARD") {
    return user.ward_name || "Ward-scoped access";
  }

  if (user.scope_type === "BROAD") {
    return "Migori County";
  }

  return user.ward_name || "No explicit scope assigned";
}

function getTwoFactorLabel(user: CurrentUser) {
  if (user.two_factor_policy === "NONE") {
    return "Not required for this role";
  }

  if (user.is_totp_enabled) {
    return user.two_factor_policy === "REQUIRED" ? "Required and enabled" : "Optional and enabled";
  }

  return user.two_factor_policy === "REQUIRED" ? "Required but not enrolled" : "Optional and not enabled";
}

function getActivityTone(status: ProfileActivityEvent["status"]) {
  if (status === "SUCCESS") {
    return "success" as const;
  }

  if (status === "FAILED" || status === "FAILURE") {
    return "danger" as const;
  }

  return "info" as const;
}

function getRecoveryCodeTone(recoveryStatus: { remaining_count: number; total_count: number } | undefined) {
  if (!recoveryStatus) {
    return "default" as const;
  }

  if (recoveryStatus.remaining_count === 0) {
    return "danger" as const;
  }

  if (recoveryStatus.remaining_count <= Math.max(2, Math.floor(recoveryStatus.total_count * 0.25))) {
    return "warning" as const;
  }

  return "success" as const;
}

function getSessionTone(status: ProfileSessionRecord["status"]) {
  if (status === "current") {
    return "success" as const;
  }

  if (status === "suspicious") {
    return "warning" as const;
  }

  if (status === "revoked") {
    return "danger" as const;
  }

  if (status === "active") {
    return "info" as const;
  }

  return "default" as const;
}

function getSessionStatusLabel(status: ProfileSessionRecord["status"]) {
  if (status === "current") {
    return "Current";
  }

  if (status === "suspicious") {
    return "Suspicious";
  }

  if (status === "revoked") {
    return "Revoked";
  }

  if (status === "expired") {
    return "Expired";
  }

  return "Active";
}

function getSessionIcon(session: ProfileSessionRecord) {
  if (session.status === "suspicious") {
    return ShieldAlert;
  }

  if (session.is_current) {
    return Laptop;
  }

  return Monitor;
}

function pluralizeSession(count: number) {
  return `${count} ${count === 1 ? "session" : "sessions"}`;
}

function PasswordRevealInput({
  id,
  label,
  value,
  onChange,
  headerActions,
  autoComplete,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  headerActions?: ReactNode;
  autoComplete?: string;
}) {
  const [isVisible, setIsVisible] = useState(false);
  const toggleLabel = `${isVisible ? "Hide" : "Show"} ${label}`;
  const ToggleIcon = isVisible ? EyeOff : Eye;

  return (
    <div className="block">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label htmlFor={id} className="text-sm font-semibold text-panel-copy">
          {label}
        </label>
        {headerActions}
      </div>
      <div className="relative mt-2">
        <input
          id={id}
          type={isVisible ? "text" : "password"}
          value={value}
          autoComplete={autoComplete}
          onChange={(event) => onChange(event.target.value)}
          className="h-12 w-full rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 pr-12 text-sm font-medium text-panel-strong outline-none focus:border-brand"
          required
        />
        <button
          type="button"
          aria-label={toggleLabel}
          title={toggleLabel}
          onClick={() => setIsVisible((current) => !current)}
          className="absolute inset-y-0 right-3 inline-flex items-center justify-center text-panel-muted transition hover:text-panel-strong"
        >
          <ToggleIcon className="size-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

function CapabilityNote() {
  return (
    <Card className="rounded-[1.5rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-5 py-5 shadow-none">
      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
        Available on this page
      </p>
      <p className="mt-3 text-sm leading-6 text-panel-muted">
        You can review your account details, security status, display preference, and recent account activity here.
      </p>
      <p className="mt-3 text-sm font-semibold text-panel-copy">
        Personal detail edits require two-factor verification before the fields unlock.
      </p>
    </Card>
  );
}

export default function ProfilePage() {
  const router = useRouter();
  const { currentUser: rawCurrentUser, logout, updateAppearance, updateProfile } = useAuth();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [isSavingAppearance, setIsSavingAppearance] = useState(false);
  const [appearanceError, setAppearanceError] = useState<string | null>(null);
  const [identityModalOpen, setIdentityModalOpen] = useState(false);
  const [identityCode, setIdentityCode] = useState("");
  const lastIdentityVerificationCodeRef = useRef<string | null>(null);
  const [identityVerifyError, setIdentityVerifyError] = useState<string | null>(null);
  const [isVerifyingIdentity, setIsVerifyingIdentity] = useState(false);
  const [isIdentityUnlocked, setIsIdentityUnlocked] = useState(false);
  const [isEditingIdentity, setIsEditingIdentity] = useState(false);
  const [identityUsername, setIdentityUsername] = useState("");
  const [identityFullName, setIdentityFullName] = useState("");
  const [identityEmail, setIdentityEmail] = useState("");
  const [identityPhoneNumber, setIdentityPhoneNumber] = useState("");
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [identitySuccess, setIdentitySuccess] = useState<string | null>(null);
  const [isSavingIdentity, setIsSavingIdentity] = useState(false);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [generatedPassword, setGeneratedPassword] = useState<string | null>(null);
  const [passwordGeneratorMessage, setPasswordGeneratorMessage] = useState<string | null>(null);
  const [recoveryStatusModalOpen, setRecoveryStatusModalOpen] = useState(false);
  const [recoveryModalOpen, setRecoveryModalOpen] = useState(false);
  const [recoveryCurrentPassword, setRecoveryCurrentPassword] = useState("");
  const [recoveryVerificationCode, setRecoveryVerificationCode] = useState("");
  const [isRegeneratingRecoveryCodes, setIsRegeneratingRecoveryCodes] = useState(false);
  const [generatedRecoveryCodes, setGeneratedRecoveryCodes] = useState<string[]>([]);
  const [recoveryCodesSaved, setRecoveryCodesSaved] = useState(false);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);
  const [recoverySuccess, setRecoverySuccess] = useState<string | null>(null);
  const [recoveryCopyMessage, setRecoveryCopyMessage] = useState<string | null>(null);
  const [activityFilters, setActivityFilters] = useState<Required<ProfileActivityFilters>>({
    page: 1,
    page_size: 10,
    event_type: "",
    status: "",
    date_from: "",
    date_to: "",
    security_only: true,
    include_refresh_events: false,
  });
  const [sessionActionPending, setSessionActionPending] = useState<string | null>(null);
  const [sessionActionError, setSessionActionError] = useState<string | null>(null);
  const [sessionActionSuccess, setSessionActionSuccess] = useState<string | null>(null);

  const currentUser = rawCurrentUser ? normalizeCurrentUser(rawCurrentUser) : null;

  useEffect(() => {
    if (!currentUser || isEditingIdentity) {
      return;
    }

    setIdentityUsername(currentUser.username);
    setIdentityFullName(currentUser.full_name || "");
    setIdentityEmail(currentUser.email || "");
    setIdentityPhoneNumber(currentUser.phone_number || "");
  }, [currentUser, isEditingIdentity]);

  async function submitIdentityVerification(code: string, options: { force?: boolean } = {}) {
    const codeToVerify = code.replace(/\D/g, "").slice(0, 6);

    if (codeToVerify.length !== 6) {
      return;
    }

    if (!options.force && lastIdentityVerificationCodeRef.current === codeToVerify) {
      return;
    }

    lastIdentityVerificationCodeRef.current = codeToVerify;
    setIdentityVerifyError(null);
    setIsVerifyingIdentity(true);

    try {
      await verifyProfileIdentityTwoFactorViaBff(codeToVerify);
      setIdentityCode("");
      lastIdentityVerificationCodeRef.current = null;
      setIdentityModalOpen(false);
      setIsIdentityUnlocked(true);
      setIsEditingIdentity(true);
      setIdentityError(null);
      setIdentitySuccess(null);
    } catch (error) {
      setIdentityVerifyError(error instanceof Error ? error.message : "Unable to verify your code right now.");
    } finally {
      setIsVerifyingIdentity(false);
    }
  }

  useEffect(() => {
    if (!identityModalOpen || isVerifyingIdentity) {
      return;
    }

    const codeToVerify = identityCode.replace(/\D/g, "").slice(0, 6);

    if (codeToVerify.length < 6) {
      lastIdentityVerificationCodeRef.current = null;
      return;
    }

    void submitIdentityVerification(codeToVerify);
  }, [identityCode, identityModalOpen, isVerifyingIdentity]);

  const activityQuery = useQuery({
    queryKey: queryKeys.auth.activity(activityFilters),
    queryFn: () => fetchProfileActivityViaBff(activityFilters),
    enabled: Boolean(currentUser?.profile_capabilities?.can_view_own_activity),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
  const sessionsQuery = useQuery({
    queryKey: queryKeys.auth.sessions(),
    queryFn: fetchProfileSessionsViaBff,
    enabled: Boolean(currentUser?.profile_capabilities?.can_review_sessions),
    staleTime: 60_000,
  });
  const recoveryStatusQuery = useQuery({
    queryKey: queryKeys.auth.recoveryCodes(),
    queryFn: fetchRecoveryCodeStatusViaBff,
    enabled: Boolean(
      currentUser?.is_totp_enabled === true &&
        currentUser?.profile_capabilities?.can_manage_totp === true,
    ),
    staleTime: 60_000,
  });

  if (!currentUser) {
    return null;
  }

  const capabilities = currentUser.profile_capabilities;
  const displayName = currentUser.full_name || currentUser.username;
  const initials = getInitials(displayName || currentUser.username);
  const scopeLabel = getScopeLabel(currentUser);
  const twoFactorLabel = getTwoFactorLabel(currentUser);
  const canChangePassword = capabilities?.can_change_password === true;
  const canUpdateAppearance = capabilities?.can_update_appearance === true;
  const canUpdateIdentity = capabilities?.can_update_identity === true;
  const canManageTotp = capabilities?.can_manage_totp === true;
  const canViewActivity = capabilities?.can_view_own_activity === true;
  const canReviewSessions = capabilities?.can_review_sessions === true;
  const capabilityContractReady = Boolean(capabilities);
  const recoveryStatus = recoveryStatusQuery.data;
  const recoveryCodeTone = getRecoveryCodeTone(recoveryStatus);
  const sessionData = sessionsQuery.data;
  const sessions = sessionData?.sessions ?? [];
  const activeSessions = sessions.filter((session) => session.is_active);
  const otherActiveSessions = sessions.filter((session) => session.is_active && !session.is_current);
  const activityData = activityQuery.data;
  const activityEvents = activityData?.results ?? activityData?.events ?? [];
  const activityCount = activityData?.count ?? activityEvents.length;
  const activityTotalPages = Math.max(1, Math.ceil(activityCount / activityFilters.page_size));
  const hasActiveActivityFilters = Boolean(
    activityFilters.event_type ||
      activityFilters.status ||
      activityFilters.date_from ||
      activityFilters.date_to ||
      activityFilters.include_refresh_events ||
      !activityFilters.security_only,
  );

  const detailItems = [
    { label: "Username", value: currentUser.username },
    { label: "Full name", value: currentUser.full_name || "Not provided" },
    { label: "Email address", value: currentUser.email || "Not provided" },
    { label: "Phone number", value: currentUser.phone_number || "Not provided" },
    { label: "Scope", value: scopeLabel },
    { label: "Account created", value: formatDateTime(currentUser.account_created_at) },
    { label: "Last login", value: formatDateTime(currentUser.last_login_at) },
  ];

  async function handleSignOut() {
    setIsSigningOut(true);

    try {
      await logout();
      router.replace("/login");
    } finally {
      setIsSigningOut(false);
    }
  }

  async function executeSessionActionWithStepUp(action: () => Promise<ProfileSessionRevokeResponse>) {
    try {
      return await action();
    } catch (error) {
      if (error instanceof AuthStepUpRequiredError) {
        await requestStepUp(error.purpose);
        return action();
      }

      throw error;
    }
  }

  async function refetchSessionSecurityData() {
    const refetches: Array<Promise<unknown>> = [sessionsQuery.refetch()];
    if (canViewActivity) {
      refetches.push(activityQuery.refetch());
    }
    await Promise.all(refetches);
  }

  async function handleRevokeSession(publicId: string) {
    if (sessionActionPending) {
      return;
    }

    setSessionActionPending(publicId);
    setSessionActionError(null);
    setSessionActionSuccess(null);

    try {
      const response = await executeSessionActionWithStepUp(() => revokeProfileSessionViaBff(publicId));
      if (response.current_session_revoked) {
        await logout().catch(() => undefined);
        router.replace("/login");
        return;
      }
      setSessionActionSuccess("Session revoked.");
      await refetchSessionSecurityData();
    } catch (error) {
      setSessionActionError(error instanceof Error ? error.message : "Unable to revoke this session right now.");
    } finally {
      setSessionActionPending(null);
    }
  }

  async function handleRevokeOtherSessions() {
    if (sessionActionPending || otherActiveSessions.length === 0) {
      return;
    }

    setSessionActionPending("others");
    setSessionActionError(null);
    setSessionActionSuccess(null);

    try {
      const response = await executeSessionActionWithStepUp(revokeOtherProfileSessionsViaBff);
      setSessionActionSuccess(`${pluralizeSession(response.revoked_count)} signed out.`);
      await refetchSessionSecurityData();
    } catch (error) {
      setSessionActionError(error instanceof Error ? error.message : "Unable to revoke other sessions right now.");
    } finally {
      setSessionActionPending(null);
    }
  }

  async function handleRevokeAllSessions() {
    if (sessionActionPending) {
      return;
    }

    setSessionActionPending("all");
    setSessionActionError(null);
    setSessionActionSuccess(null);

    try {
      await executeSessionActionWithStepUp(revokeAllProfileSessionsViaBff);
      await logout().catch(() => undefined);
      router.replace("/login");
    } catch (error) {
      setSessionActionError(error instanceof Error ? error.message : "Unable to revoke sessions right now.");
    } finally {
      setSessionActionPending(null);
    }
  }

  async function handleAppearanceChange(themePreference: ThemePreference) {
    if (!canUpdateAppearance || isSavingAppearance || themePreference === currentUser?.theme_preference) {
      return;
    }

    setAppearanceError(null);
    setIsSavingAppearance(true);

    try {
      await updateAppearance(themePreference);
    } catch (error) {
      setAppearanceError(
        error instanceof Error ? error.message : "Unable to save your appearance preference right now.",
      );
    } finally {
      setIsSavingAppearance(false);
    }
  }

  async function handleIdentityVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitIdentityVerification(identityCode, { force: true });
  }

  async function handleIdentitySave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIdentityError(null);
    setIdentitySuccess(null);

    const trimmedUsername = identityUsername.trim();

    if (!trimmedUsername) {
      setIdentityError("Login username cannot be blank.");
      return;
    }

    if (!isValidUsername(trimmedUsername)) {
      setIdentityError("Login username can only use letters, numbers, and @ . + - _ characters.");
      return;
    }

    setIsSavingIdentity(true);

    try {
      await updateProfile({
        username: trimmedUsername,
        full_name: identityFullName,
        email: identityEmail,
        phone_number: identityPhoneNumber,
      });
      setIsEditingIdentity(false);
      setIsIdentityUnlocked(false);
      setIdentitySuccess("Personal details updated successfully.");
    } catch (error) {
      setIdentityError(error instanceof Error ? error.message : "Unable to update personal details right now.");
      if (error instanceof Error && /verify two-factor/i.test(error.message)) {
        setIsIdentityUnlocked(false);
      }
    } finally {
      setIsSavingIdentity(false);
    }
  }

  function handleIdentityCancel() {
    if (!currentUser) {
      return;
    }

    setIdentityUsername(currentUser.username);
    setIdentityFullName(currentUser.full_name || "");
    setIdentityEmail(currentUser.email || "");
    setIdentityPhoneNumber(currentUser.phone_number || "");
    setIsEditingIdentity(false);
    setIdentityError(null);
  }

  function handleNewPasswordInput(value: string) {
    setNewPassword(value);
    setGeneratedPassword(null);
    setPasswordGeneratorMessage(null);
  }

  function resetPasswordForm() {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setGeneratedPassword(null);
    setPasswordGeneratorMessage(null);
    setPasswordError(null);
  }

  function closePasswordModal() {
    setPasswordModalOpen(false);
    resetPasswordForm();
  }

  function handleGeneratePassword() {
    try {
      const generated = generateStrongPassword();

      setNewPassword(generated);
      setConfirmPassword(generated);
      setGeneratedPassword(generated);
      setPasswordError(null);
      setPasswordGeneratorMessage("Generated and filled a strong password. Copy it before saving.");
    } catch (error) {
      setPasswordError(
        error instanceof Error ? error.message : "Secure password generation is unavailable in this browser.",
      );
    }
  }

  async function handleCopyGeneratedPassword() {
    if (!generatedPassword) {
      return;
    }

    if (!navigator.clipboard?.writeText) {
      setPasswordError("Clipboard access is unavailable in this browser.");
      return;
    }

    try {
      await navigator.clipboard.writeText(generatedPassword);
      setPasswordError(null);
      setPasswordGeneratorMessage("Generated password copied.");
    } catch {
      setPasswordError("Unable to copy the generated password.");
    }
  }

  async function handlePasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(null);

    if (newPassword !== confirmPassword) {
      setPasswordError("The new password and confirmation do not match.");
      return;
    }

    const passwordPolicyError = getPasswordPolicyError(newPassword);

    if (passwordPolicyError) {
      setPasswordError(passwordPolicyError);
      return;
    }

    setIsChangingPassword(true);

    try {
      const response = await changePasswordViaBff({
        current_password: currentPassword,
        new_password: newPassword,
      });

      resetPasswordForm();
      setPasswordSuccess(`${response.detail} You may be asked to sign in again on your next request.`);
      setPasswordModalOpen(false);
    } catch (error) {
      setPasswordError(error instanceof Error ? error.message : "Unable to change your password right now.");
    } finally {
      setIsChangingPassword(false);
    }
  }

  async function handleRecoveryCodeRegeneration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRecoveryError(null);
    setRecoverySuccess(null);
    setRecoveryCopyMessage(null);
    setIsRegeneratingRecoveryCodes(true);

    try {
      const response = await regenerateRecoveryCodesViaBff({
        current_password: recoveryCurrentPassword,
        code: recoveryVerificationCode,
      });

      setGeneratedRecoveryCodes(response.recovery_codes);
      setRecoveryCodesSaved(false);
      setRecoveryCurrentPassword("");
      setRecoveryVerificationCode("");
      setRecoverySuccess("Recovery codes regenerated. Save the new codes before closing.");
      await recoveryStatusQuery.refetch();
    } catch (error) {
      setRecoveryError(error instanceof Error ? error.message : "Unable to regenerate recovery codes right now.");
    } finally {
      setIsRegeneratingRecoveryCodes(false);
    }
  }

  async function handleCopyGeneratedRecoveryCodes() {
    if (generatedRecoveryCodes.length === 0) {
      return;
    }

    try {
      await navigator.clipboard.writeText(generatedRecoveryCodes.join("\n"));
      setRecoveryCodesSaved(true);
      setRecoveryCopyMessage("Copied");
    } catch {
      setRecoveryCopyMessage("Copy unavailable");
    }
  }

  function handleDownloadGeneratedRecoveryCodes() {
    if (generatedRecoveryCodes.length === 0) {
      return;
    }

    const blob = new Blob(
      [
        [
          "CCHIS recovery codes",
          "",
          ...generatedRecoveryCodes,
          "",
          "Each code can be used once.",
        ].join("\n"),
      ],
      { type: "text/plain" },
    );
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "cchis-recovery-codes.txt";
    link.click();
    window.URL.revokeObjectURL(url);
    setRecoveryCodesSaved(true);
    setRecoveryCopyMessage("Download started");
  }

  function openRecoveryRegenerationModal() {
    setRecoveryStatusModalOpen(false);
    setRecoveryError(null);
    setRecoverySuccess(null);
    setRecoveryCopyMessage(null);
    setGeneratedRecoveryCodes([]);
    setRecoveryCodesSaved(false);
    setRecoveryModalOpen(true);
  }

  function closeRecoveryModal() {
    setRecoveryModalOpen(false);
    setRecoveryCurrentPassword("");
    setRecoveryVerificationCode("");
    setGeneratedRecoveryCodes([]);
    setRecoveryCodesSaved(false);
    setRecoveryError(null);
    setRecoveryCopyMessage(null);
  }

  function requestCloseRecoveryModal() {
    if (generatedRecoveryCodes.length > 0 && !recoveryCodesSaved) {
      setRecoveryError("Save these recovery codes before closing this window.");
      return;
    }

    closeRecoveryModal();
  }

  function updateActivityFilters(nextFilters: Partial<Required<ProfileActivityFilters>>) {
    setActivityFilters((currentFilters) => ({
      ...currentFilters,
      ...nextFilters,
      page: nextFilters.page ?? 1,
    }));
  }

  function resetActivityFilters() {
    setActivityFilters({
      page: 1,
      page_size: 10,
      event_type: "",
      status: "",
      date_from: "",
      date_to: "",
      security_only: true,
      include_refresh_events: false,
    });
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar title="Profile" subtitle="Account, security, and preferences" lastUpdatedLabel="Profile shown" />

      {appearanceError ? <StatusBanner tone="danger">{appearanceError}</StatusBanner> : null}
      {identityError ? <StatusBanner tone="danger">{identityError}</StatusBanner> : null}
      {identitySuccess ? <StatusBanner tone="success">{identitySuccess}</StatusBanner> : null}
      {passwordSuccess ? <StatusBanner tone="success">{passwordSuccess}</StatusBanner> : null}
      {recoverySuccess ? <StatusBanner tone="success">{recoverySuccess}</StatusBanner> : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_24rem]">
        <Card className="rounded-[2rem] px-6 py-6">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-start gap-4">
              <div className="relative">
                <div className="flex size-[5.25rem] items-center justify-center rounded-[1.35rem] bg-[linear-gradient(180deg,#2d7f89_0%,#1d5375_100%)] text-[1.5rem] font-semibold tracking-[-0.04em] text-white shadow-[0_20px_36px_rgba(27,79,115,0.24)]">
                  {initials}
                </div>
                <span className="absolute -bottom-1.5 -right-1.5 inline-flex size-7 items-center justify-center rounded-full bg-brand text-white shadow-[0_10px_18px_rgba(23,95,194,0.24)]">
                  <UserRound className="size-3.5" aria-hidden="true" />
                </span>
              </div>

              <div className="space-y-4">
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="text-[1.75rem] font-semibold tracking-[-0.05em] text-panel-strong">
                      {displayName}
                    </h2>
                    <StatusBadge tone="info">{currentUser.role.replaceAll("_", " ")}</StatusBadge>
                    <StatusBadge tone={currentUser.is_active ? "success" : "danger"}>
                      {currentUser.is_active ? "Active" : "Inactive"}
                    </StatusBadge>
                  </div>
                  <p className="mt-1 text-sm font-medium text-panel-muted">Signed-in account summary</p>
                </div>

                <div className="grid gap-2 text-sm text-panel-copy sm:grid-cols-2">
                  <span className="inline-flex items-center gap-2">
                    <MapPinned className="size-4 text-brand" aria-hidden="true" />
                    {scopeLabel}
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <ShieldCheck className="size-4 text-brand" aria-hidden="true" />
                    {twoFactorLabel}
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <CalendarClock className="size-4 text-brand" aria-hidden="true" />
                    Created: {formatDateTime(currentUser.account_created_at)}
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <Clock3 className="size-4 text-brand" aria-hidden="true" />
                    Last login: {formatDateTime(currentUser.last_login_at)}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-3 lg:justify-end">
              {canManageTotp && !currentUser.is_totp_enabled ? (
                <Link
                  href="/setup-2fa"
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                >
                  <KeyRound className="size-4" aria-hidden="true" />
                  Set up TOTP
                </Link>
              ) : null}

              <Button
                variant="secondary"
                onClick={() => {
                  void handleSignOut();
                }}
                disabled={isSigningOut}
              >
                <LogOut className="size-4" aria-hidden="true" />
                {isSigningOut ? "Signing out..." : "Sign out"}
              </Button>
            </div>
          </div>
        </Card>

        <CapabilityNote />
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_24rem]">
        <Card className="rounded-[2rem] px-6 py-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">Account details</h2>
              <p className="mt-1 text-sm text-panel-muted">
                Personal details can be edited after two-factor verification.
              </p>
            </div>

            {isEditingIdentity ? (
              <StatusBadge tone="success">2FA verified</StatusBadge>
            ) : canUpdateIdentity ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setIdentityVerifyError(null);
                  setIdentityModalOpen(true);
                }}
              >
                <Edit3 className="size-4" aria-hidden="true" />
                Edit details
              </Button>
            ) : (
              <StatusBadge tone="default">2FA required</StatusBadge>
            )}
          </div>

          {isEditingIdentity && isIdentityUnlocked ? (
            <form className="mt-6 grid gap-3 sm:grid-cols-2" onSubmit={handleIdentitySave}>
              <label className="block rounded-[1.2rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-4 py-4">
                <span className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  Login username
                </span>
                <input
                  value={identityUsername}
                  onChange={(event) => setIdentityUsername(event.target.value)}
                  autoComplete="username"
                  pattern="[A-Za-z0-9@.+_-]+"
                  className="mt-2 h-10 w-full rounded-[0.8rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-strong outline-none focus:border-brand"
                  required
                />
              </label>
              <label className="block rounded-[1.2rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-4 py-4">
                <span className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  Full name
                </span>
                <input
                  value={identityFullName}
                  onChange={(event) => setIdentityFullName(event.target.value)}
                  className="mt-2 h-10 w-full rounded-[0.8rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-strong outline-none focus:border-brand"
                />
              </label>
              <label className="block rounded-[1.2rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-4 py-4">
                <span className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  Email address
                </span>
                <input
                  type="email"
                  value={identityEmail}
                  onChange={(event) => setIdentityEmail(event.target.value)}
                  className="mt-2 h-10 w-full rounded-[0.8rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-strong outline-none focus:border-brand"
                  required
                />
              </label>
              <label className="block rounded-[1.2rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-4 py-4">
                <span className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  Phone number
                </span>
                <input
                  value={identityPhoneNumber}
                  onChange={(event) => setIdentityPhoneNumber(event.target.value)}
                  className="mt-2 h-10 w-full rounded-[0.8rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-strong outline-none focus:border-brand"
                />
              </label>
              <div className="flex flex-wrap justify-end gap-3 sm:col-span-2">
                <Button variant="secondary" onClick={handleIdentityCancel}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSavingIdentity}>
                  <Save className="size-4" aria-hidden="true" />
                  {isSavingIdentity ? "Saving..." : "Save details"}
                </Button>
              </div>
            </form>
          ) : (
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {detailItems.map((item) => (
                <div
                  key={item.label}
                  className="rounded-[1.2rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-4 py-4"
                >
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                    {item.label}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-panel-strong">{item.value}</p>
                </div>
              ))}
            </div>
          )}

          {!canUpdateIdentity ? (
            <p className="mt-4 text-sm text-panel-muted">
              Set up two-factor authentication before editing personal details.
            </p>
          ) : null}
        </Card>

        <Card className="rounded-[2rem] px-5 py-6">
          <div>
            <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">Preferences</h2>
            <p className="mt-1 text-sm text-panel-muted">Your saved display preference.</p>
          </div>

          <div className="mt-5 rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] px-4 py-4">
            <span className="flex items-center gap-3">
              <MonitorCog className="size-4 text-panel-muted" aria-hidden="true" />
              <span>
                <span className="block text-sm font-semibold text-panel-copy">Appearance</span>
                <span className="mt-1 block text-xs font-medium text-panel-muted">
                  {isSavingAppearance ? "Saving preference..." : "Saved display preference"}
                </span>
              </span>
            </span>

            <div
              className="mt-4 grid grid-cols-3 gap-1 rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-1"
              aria-label="Appearance preference"
            >
              {appearanceOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    void handleAppearanceChange(option.value);
                  }}
                  disabled={!canUpdateAppearance || isSavingAppearance}
                  aria-pressed={currentUser.theme_preference === option.value}
                  className={[
                    "inline-flex min-h-10 items-center justify-center gap-2 rounded-[0.8rem] px-2.5 py-2 text-xs font-semibold transition",
                    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
                    currentUser.theme_preference === option.value
                      ? "bg-brand text-white shadow-[0_10px_22px_rgba(59,130,246,0.28)]"
                      : "text-panel-muted hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] hover:text-panel-strong",
                    !canUpdateAppearance || isSavingAppearance ? "cursor-not-allowed opacity-60" : "",
                  ].join(" ")}
                >
                  <option.Icon className="size-4" aria-hidden="true" />
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {!capabilityContractReady ? (
            <p className="mt-4 text-sm text-panel-muted">Refreshing account permissions...</p>
          ) : !canUpdateAppearance ? (
            <p className="mt-4 text-sm text-panel-muted">Appearance changes are not available for this account state.</p>
          ) : null}
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_24rem]">
        <Card className="rounded-[2rem] px-6 py-6">
          <div>
            <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">
              Security & authentication
            </h2>
            <p className="mt-1 text-sm text-panel-muted">Password and two-factor settings for this account.</p>
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <Card className="rounded-[1.5rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-5 py-5 shadow-none">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--brand)_18%,transparent)] text-brand">
                  <KeyRound className="size-4" aria-hidden="true" />
                </span>
                <strong className="text-base font-semibold text-panel-strong">Password</strong>
              </div>
              <p className="mt-4 min-h-[3.75rem] text-sm leading-6 text-panel-muted">
                Change your password securely by confirming your current password first.
              </p>
              {canChangePassword ? (
                <button
                  type="button"
                  onClick={() => {
                    setPasswordError(null);
                    setPasswordSuccess(null);
                    setPasswordModalOpen(true);
                  }}
                  className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
                >
                  Change password
                  <ChevronRight className="size-4" aria-hidden="true" />
                </button>
              ) : (
                <p className="mt-4 text-sm text-panel-muted">Password changes are not available for this account state.</p>
              )}
            </Card>

            <Card className="rounded-[1.5rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-5 py-5 shadow-none">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_20%,transparent)] text-[color:var(--warning)]">
                  <ShieldCheck className="size-4" aria-hidden="true" />
                </span>
                <strong className="text-base font-semibold text-panel-strong">Two-factor</strong>
              </div>
              <p className="mt-4 min-h-[3.75rem] text-sm leading-6 text-panel-muted">
                {twoFactorLabel}. Setup appears only when your account policy permits it.
              </p>
              {currentUser.is_totp_enabled && canManageTotp ? (
                <div className="mt-4 rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3">
                  <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                    Recovery codes
                  </span>
                  <span className="mt-1 block text-sm font-semibold text-panel-copy">
                    {recoveryStatusQuery.isPending
                      ? "Loading..."
                      : recoveryStatusQuery.isError
                        ? "Unavailable"
                        : recoveryStatus
                          ? `${recoveryStatus.remaining_count} of ${recoveryStatus.total_count} remaining`
                          : "No codes recorded"}
                  </span>
                  {recoveryStatus?.last_generated_at ? (
                    <span className="mt-1 block text-xs font-medium text-panel-muted">
                      Last generated {formatDateTime(recoveryStatus.last_generated_at)}
                    </span>
                  ) : null}
                  {recoveryStatus?.last_used_at ? (
                    <span className="mt-1 block text-xs font-medium text-panel-muted">
                      Last used {formatDateTime(recoveryStatus.last_used_at)}
                    </span>
                  ) : null}
                </div>
              ) : null}
              {canManageTotp && !currentUser.is_totp_enabled ? (
                <Link
                  href="/setup-2fa"
                  className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
                >
                  Open TOTP setup
                  <ChevronRight className="size-4" aria-hidden="true" />
                </Link>
              ) : (
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <StatusBadge tone={currentUser.is_totp_enabled ? "success" : "default"}>
                    {currentUser.is_totp_enabled ? "Enabled" : "No setup required"}
                  </StatusBadge>
                  {currentUser.is_totp_enabled && canManageTotp ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      type="button"
                      onClick={() => {
                        setRecoveryStatusModalOpen(true);
                      }}
                    >
                      <KeyRound className="size-4" aria-hidden="true" />
                      Recovery codes
                    </Button>
                  ) : null}
                  {currentUser.is_totp_enabled && canManageTotp ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      type="button"
                      onClick={openRecoveryRegenerationModal}
                      disabled={recoveryStatus?.can_regenerate === false}
                    >
                      <RefreshCw className="size-4" aria-hidden="true" />
                      Regenerate codes
                    </Button>
                  ) : null}
                </div>
              )}
            </Card>
          </div>
        </Card>

        <Card className="rounded-[2rem] px-5 py-6">
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
            Managed by administrator
          </p>
          <p className="mt-3 text-sm leading-6 text-panel-muted">
            Identity recovery, account deactivation, saved alert preferences, and profile report generation are handled
            through administrator-managed workflows.
          </p>
        </Card>
      </section>

      <section>
        <Card className="rounded-[2rem] px-6 py-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">Active sessions</h2>
              <p className="mt-1 text-sm text-panel-muted">
                Devices and browsers with recent access to this account.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge tone="info">{pluralizeSession(activeSessions.length)} active</StatusBadge>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  void handleRevokeOtherSessions();
                }}
                disabled={!canReviewSessions || otherActiveSessions.length === 0 || Boolean(sessionActionPending)}
              >
                <Users className="size-4" aria-hidden="true" />
                {sessionActionPending === "others" ? "Signing out..." : "Sign out other devices"}
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => {
                  void handleRevokeAllSessions();
                }}
                disabled={!canReviewSessions || sessions.length === 0 || Boolean(sessionActionPending)}
              >
                <Trash2 className="size-4" aria-hidden="true" />
                {sessionActionPending === "all" ? "Signing out..." : "Sign out all devices"}
              </Button>
            </div>
          </div>

          {sessionActionError ? <StatusBanner tone="danger" className="mt-5">{sessionActionError}</StatusBanner> : null}
          {sessionActionSuccess ? <StatusBanner tone="success" className="mt-5">{sessionActionSuccess}</StatusBanner> : null}

          <div className="mt-6">
            {!capabilityContractReady ? (
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                Refreshing account permissions...
              </div>
            ) : !canReviewSessions ? (
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                Session review is not available for this account state.
              </div>
            ) : sessionsQuery.isPending ? (
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                Loading active sessions...
              </div>
            ) : sessionsQuery.isError ? (
              <div className="rounded-[1.35rem] border border-[color-mix(in_srgb,var(--danger)_42%,transparent)] bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] px-4 py-5 text-sm text-panel-muted">
                Unable to load active sessions right now.
              </div>
            ) : sessions.length === 0 ? (
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                No active sessions have been recorded yet.
              </div>
            ) : (
              <div className="overflow-hidden rounded-[1.35rem] border border-panel-table-wrap">
                {sessions.map((session) => {
                  const SessionIcon = getSessionIcon(session);
                  const sessionPending = sessionActionPending === session.public_id;

                  return (
                    <div
                      key={session.public_id}
                      className="grid gap-4 border-b border-[var(--dashboard-table-line)] px-4 py-4 last:border-b-0 lg:grid-cols-[minmax(0,1.15fr)_minmax(15rem,0.85fr)_auto]"
                    >
                      <div className="min-w-0">
                        <div className="flex items-start gap-3">
                          <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--brand)_14%,transparent)] text-brand">
                            <SessionIcon className="size-4" aria-hidden="true" />
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold text-panel-strong">
                              {session.is_current ? "This device" : session.device_label}
                            </span>
                            <span className="mt-1 block break-words text-sm text-panel-muted">
                              {session.browser_label}
                            </span>
                          </span>
                        </div>

                        {session.is_suspicious ? (
                          <span className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-[color:var(--warning)]">
                            <AlertTriangle className="size-4" aria-hidden="true" />
                            {session.suspicion_reason
                              ? session.suspicion_reason.replaceAll("_", " ")
                              : "Context changed"}
                          </span>
                        ) : null}
                      </div>

                      <div className="grid gap-2 text-sm text-panel-muted sm:grid-cols-2 lg:grid-cols-1">
                        <span className="inline-flex items-center gap-2">
                          <CalendarClock className="size-4 text-brand" aria-hidden="true" />
                          Created {formatDateTime(session.created_at)}
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <Clock3 className="size-4 text-brand" aria-hidden="true" />
                          Last active {formatDateTime(session.last_seen_at)}
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <Globe2 className="size-4 text-brand" aria-hidden="true" />
                          {session.location_label}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-3 lg:justify-end">
                        <StatusBadge tone={getSessionTone(session.status)}>
                          {getSessionStatusLabel(session.status)}
                        </StatusBadge>
                        {session.is_current && session.is_active ? (
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => {
                              void handleSignOut();
                            }}
                            disabled={isSigningOut}
                          >
                            <LogOut className="size-4" aria-hidden="true" />
                            {isSigningOut ? "Signing out..." : "Sign out this device"}
                          </Button>
                        ) : session.is_active ? (
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => {
                              void handleRevokeSession(session.public_id);
                            }}
                            disabled={Boolean(sessionActionPending)}
                          >
                            <LogOut className="size-4" aria-hidden="true" />
                            {sessionPending ? "Signing out..." : "Sign out"}
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </Card>
      </section>

      <section>
        <Card className="rounded-[2rem] px-6 py-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">Account activity</h2>
              <p className="mt-1 text-sm text-panel-muted">Recent sign-in and security events for this account.</p>
            </div>
            <StatusBadge tone="info">Read-only</StatusBadge>
          </div>

          {canViewActivity ? (
            <div className="mt-6 space-y-4">
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1.25fr)_9rem_9rem_9rem]">
                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                    Event type
                  </span>
                  <select
                    aria-label="Activity event type"
                    value={activityFilters.event_type}
                    onChange={(event) => updateActivityFilters({ event_type: event.target.value })}
                    className="mt-2 h-11 w-full rounded-[0.9rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy outline-none focus:border-brand"
                  >
                    <option value="">All events</option>
                    {activityEventOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                    Status
                  </span>
                  <select
                    aria-label="Activity status"
                    value={activityFilters.status}
                    onChange={(event) => updateActivityFilters({ status: event.target.value })}
                    className="mt-2 h-11 w-full rounded-[0.9rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy outline-none focus:border-brand"
                  >
                    <option value="">All</option>
                    <option value="SUCCESS">Success</option>
                    <option value="FAILED">Failed</option>
                  </select>
                </label>

                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                    From
                  </span>
                  <input
                    type="date"
                    aria-label="Activity from date"
                    value={activityFilters.date_from}
                    onChange={(event) => updateActivityFilters({ date_from: event.target.value })}
                    className="mt-2 h-11 w-full rounded-[0.9rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy outline-none focus:border-brand"
                  />
                </label>

                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                    To
                  </span>
                  <input
                    type="date"
                    aria-label="Activity to date"
                    value={activityFilters.date_to}
                    onChange={(event) => updateActivityFilters({ date_to: event.target.value })}
                    className="mt-2 h-11 w-full rounded-[0.9rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy outline-none focus:border-brand"
                  />
                </label>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-3">
                  <label className="inline-flex min-h-10 items-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy">
                    <input
                      type="checkbox"
                      checked={activityFilters.include_refresh_events}
                      onChange={(event) => updateActivityFilters({ include_refresh_events: event.target.checked })}
                      className="size-4 accent-[var(--login-submit-start)]"
                    />
                    Show session refreshes
                  </label>

                  <label className="inline-flex items-center gap-2 text-sm font-semibold text-panel-copy">
                    Page size
                    <select
                      aria-label="Activity page size"
                      value={activityFilters.page_size}
                      onChange={(event) => updateActivityFilters({ page_size: Number(event.target.value) })}
                      className="h-10 rounded-[0.8rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy outline-none focus:border-brand"
                    >
                      <option value={10}>10</option>
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                    </select>
                  </label>
                </div>

                <Button variant="secondary" size="sm" onClick={resetActivityFilters} disabled={!hasActiveActivityFilters}>
                  Reset filters
                </Button>
              </div>
            </div>
          ) : null}

          <div className="mt-6">
            {!capabilityContractReady ? (
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                Refreshing account permissions...
              </div>
            ) : !canViewActivity ? (
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                Account activity is not available for this account state.
              </div>
            ) : activityQuery.isPending ? (
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                Loading account activity...
              </div>
            ) : activityQuery.isError ? (
              <div className="rounded-[1.35rem] border border-[color-mix(in_srgb,var(--danger)_42%,transparent)] bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] px-4 py-5 text-sm text-panel-muted">
                Unable to load account activity right now.
              </div>
            ) : activityEvents.length === 0 ? (
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                {hasActiveActivityFilters
                  ? "No account activity matches the current filters."
                  : "No account activity has been recorded yet."}
              </div>
            ) : (
              <div className="overflow-hidden rounded-[1.35rem] border border-panel-table-wrap">
                {activityEvents.map((event) => (
                  <div
                    key={event.id}
                    className="grid gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-4 last:border-b-0 md:grid-cols-[10rem_minmax(0,1fr)_auto]"
                  >
                    <span className="inline-flex items-center gap-2 text-sm font-semibold text-panel-muted">
                      <Activity className="size-4" aria-hidden="true" />
                      {formatDateTime(event.created_at)}
                    </span>
                    <span>
                      <span className="block text-sm font-semibold text-panel-strong">{event.title}</span>
                      <span className="mt-1 block text-sm text-panel-muted">{event.description}</span>
                    </span>
                    <StatusBadge tone={getActivityTone(event.status)}>{event.status}</StatusBadge>
                  </div>
                ))}
              </div>
            )}
          </div>

          {canViewActivity && !activityQuery.isError && activityData ? (
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-panel-muted">
              <span>
                Page {activityFilters.page} of {activityTotalPages} · {activityCount}{" "}
                {activityCount === 1 ? "event" : "events"}
              </span>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => updateActivityFilters({ page: Math.max(1, activityFilters.page - 1) })}
                  disabled={!activityData.previous || activityQuery.isFetching}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => updateActivityFilters({ page: activityFilters.page + 1 })}
                  disabled={!activityData.next || activityQuery.isFetching}
                >
                  Next
                </Button>
              </div>
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-panel-muted">
            <span className="inline-flex items-center gap-2">
              <CheckCircle2 className="size-4" aria-hidden="true" />
              Account status: {currentUser.is_active ? "Active" : "Inactive"}
            </span>
            <span className="inline-flex items-center gap-2">
              <MapPinned className="size-4" aria-hidden="true" />
              Scope: {scopeLabel}
            </span>
          </div>
        </Card>
      </section>

      {passwordModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,#020617_78%,transparent)] px-4 py-6 backdrop-blur-sm">
          <Card className="w-full max-w-xl rounded-[2rem] px-6 py-6 shadow-[0_28px_80px_rgba(0,0,0,0.35)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[0.7rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                  Password
                </p>
                <h2 className="mt-2 text-[1.45rem] font-semibold tracking-[-0.04em] text-panel-strong">
                  Change password
                </h2>
                <p className="mt-1 text-sm text-panel-muted">
                  Confirm your current password before setting a new one.
                </p>
              </div>
              <button
                type="button"
                onClick={closePasswordModal}
                className="inline-flex size-10 items-center justify-center rounded-full text-panel-muted transition hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_42%,transparent)] hover:text-panel-strong"
                aria-label="Close password modal"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>

            {passwordError ? <StatusBanner tone="danger" className="mt-5">{passwordError}</StatusBanner> : null}
            {passwordGeneratorMessage ? (
              <StatusBanner tone="info" className="mt-5">{passwordGeneratorMessage}</StatusBanner>
            ) : null}

            <form className="mt-6 space-y-4" onSubmit={handlePasswordChange}>
              <PasswordRevealInput
                id="profile_current_password"
                label="Current password"
                value={currentPassword}
                autoComplete="current-password"
                onChange={setCurrentPassword}
              />

              <PasswordRevealInput
                id="profile_new_password"
                label="New password"
                value={newPassword}
                autoComplete="new-password"
                onChange={handleNewPasswordInput}
                headerActions={
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handleGeneratePassword}
                      aria-label="Generate strong password"
                    >
                      <KeyRound className="size-4" aria-hidden="true" />
                      Generate
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => void handleCopyGeneratedPassword()}
                      disabled={!generatedPassword}
                      aria-label="Copy generated password"
                    >
                      <Copy className="size-4" aria-hidden="true" />
                      Copy
                    </Button>
                  </div>
                }
              />

              <PasswordPolicyChecklist password={newPassword} />

              <PasswordRevealInput
                id="profile_confirm_password"
                label="Confirm new password"
                value={confirmPassword}
                autoComplete="new-password"
                onChange={setConfirmPassword}
              />

              <div className="flex flex-wrap justify-end gap-3 pt-2">
                <Button
                  variant="secondary"
                  onClick={closePasswordModal}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isChangingPassword}>
                  {isChangingPassword ? "Changing..." : "Change password"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      ) : null}

      {recoveryStatusModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,#020617_78%,transparent)] px-4 py-6 backdrop-blur-sm">
          <Card className="w-full max-w-xl rounded-[2rem] px-6 py-6 shadow-[0_28px_80px_rgba(0,0,0,0.35)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[0.7rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                  Recovery codes
                </p>
                <h2 className="mt-2 text-[1.45rem] font-semibold tracking-[-0.04em] text-panel-strong">
                  Manage recovery codes
                </h2>
                <p className="mt-1 text-sm text-panel-muted">
                  Recovery codes are backup sign-in codes for when your authenticator is unavailable.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setRecoveryStatusModalOpen(false);
                }}
                className="inline-flex size-10 items-center justify-center rounded-full text-panel-muted transition hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_42%,transparent)] hover:text-panel-strong"
                aria-label="Close recovery code status"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <div className="rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3">
                <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  Remaining
                </span>
                <span className="mt-2 flex flex-wrap items-center gap-2 text-sm font-semibold text-panel-copy">
                  {recoveryStatus
                    ? `${recoveryStatus.remaining_count} of ${recoveryStatus.total_count} codes`
                    : "Status unavailable"}
                  <StatusBadge tone={recoveryCodeTone}>
                    {recoveryStatus?.remaining_count === 0 ? "Replace now" : "Available"}
                  </StatusBadge>
                </span>
              </div>
              <div className="rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3">
                <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  Last generated
                </span>
                <span className="mt-2 block text-sm font-semibold text-panel-copy">
                  {formatDateTime(recoveryStatus?.last_generated_at)}
                </span>
              </div>
              <div className="rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 sm:col-span-2">
                <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  Last used
                </span>
                <span className="mt-2 block text-sm font-semibold text-panel-copy">
                  {formatDateTime(recoveryStatus?.last_used_at)}
                </span>
              </div>
            </div>

            <StatusBanner tone="info" className="mt-5">
              You cannot view existing recovery codes again. Regenerate codes to get a new one-time set; old unused
              codes stop working immediately.
            </StatusBanner>

            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <Button
                variant="secondary"
                onClick={() => {
                  setRecoveryStatusModalOpen(false);
                }}
              >
                Close
              </Button>
              <Button
                type="button"
                onClick={openRecoveryRegenerationModal}
                disabled={recoveryStatus?.can_regenerate === false}
              >
                <RefreshCw className="size-4" aria-hidden="true" />
                Regenerate codes
              </Button>
            </div>
          </Card>
        </div>
      ) : null}

      {recoveryModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,#020617_78%,transparent)] px-4 py-6 backdrop-blur-sm">
          <Card className="max-h-[calc(100vh-3rem)] w-full max-w-2xl overflow-y-auto rounded-[2rem] px-6 py-6 shadow-[0_28px_80px_rgba(0,0,0,0.35)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[0.7rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                  Recovery codes
                </p>
                <h2 className="mt-2 text-[1.45rem] font-semibold tracking-[-0.04em] text-panel-strong">
                  Regenerate recovery codes
                </h2>
                <p className="mt-1 text-sm text-panel-muted">
                  New recovery codes replace any unused old codes.
                </p>
              </div>
              <button
                type="button"
                onClick={requestCloseRecoveryModal}
                className="inline-flex size-10 items-center justify-center rounded-full text-panel-muted transition hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_42%,transparent)] hover:text-panel-strong"
                aria-label="Close recovery codes modal"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>

            {recoveryError ? <StatusBanner tone="danger" className="mt-5">{recoveryError}</StatusBanner> : null}
            {recoveryCopyMessage ? <StatusBanner tone="info" className="mt-5">{recoveryCopyMessage}</StatusBanner> : null}

            {generatedRecoveryCodes.length > 0 ? (
              <div className="mt-6 space-y-5">
                <div className="grid gap-2 sm:grid-cols-2">
                  {generatedRecoveryCodes.map((recoveryCode) => (
                    <code
                      key={recoveryCode}
                      className="rounded-[0.9rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 py-2 text-center font-mono text-sm font-semibold text-panel-strong"
                    >
                      {recoveryCode}
                    </code>
                  ))}
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <Button type="button" variant="secondary" onClick={() => void handleCopyGeneratedRecoveryCodes()}>
                    <Copy className="size-4" aria-hidden="true" />
                    Copy codes
                  </Button>
                  <Button type="button" variant="secondary" onClick={handleDownloadGeneratedRecoveryCodes}>
                    <Download className="size-4" aria-hidden="true" />
                    Download codes
                  </Button>
                </div>

                <label className="flex items-start gap-3 rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-3 text-sm font-medium text-panel-copy">
                  <input
                    type="checkbox"
                    checked={recoveryCodesSaved}
                    onChange={(event) => setRecoveryCodesSaved(event.target.checked)}
                    className="mt-1 size-4 accent-[var(--login-submit-start)]"
                  />
                  I have saved these recovery codes.
                </label>

                <div className="flex justify-end">
                  <Button type="button" disabled={!recoveryCodesSaved} onClick={requestCloseRecoveryModal}>
                    Done
                  </Button>
                </div>
              </div>
            ) : (
              <form className="mt-6 space-y-4" onSubmit={handleRecoveryCodeRegeneration}>
                <label className="block">
                  <span className="text-sm font-semibold text-panel-copy">Current password</span>
                  <input
                    type="password"
                    value={recoveryCurrentPassword}
                    onChange={(event) => setRecoveryCurrentPassword(event.target.value)}
                    className="mt-2 h-12 w-full rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-medium text-panel-strong outline-none focus:border-brand"
                    required
                  />
                </label>

                <label className="block">
                  <span className="text-sm font-semibold text-panel-copy">Authenticator or recovery code</span>
                  <input
                    value={recoveryVerificationCode}
                    onChange={(event) => setRecoveryVerificationCode(event.target.value)}
                    autoComplete="one-time-code"
                    className="mt-2 h-12 w-full rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-medium text-panel-strong outline-none focus:border-brand"
                    required
                  />
                </label>

                <div className="flex flex-wrap justify-end gap-3 pt-2">
                  <Button variant="secondary" onClick={closeRecoveryModal}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={isRegeneratingRecoveryCodes}>
                    <RefreshCw className="size-4" aria-hidden="true" />
                    {isRegeneratingRecoveryCodes ? "Regenerating..." : "Regenerate codes"}
                  </Button>
                </div>
              </form>
            )}
          </Card>
        </div>
      ) : null}

      {identityModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,#020617_78%,transparent)] px-4 py-6 backdrop-blur-sm">
          <Card className="w-full max-w-md rounded-[2rem] px-6 py-6 shadow-[0_28px_80px_rgba(0,0,0,0.35)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[0.7rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                  Two-factor
                </p>
                <h2 className="mt-2 text-[1.45rem] font-semibold tracking-[-0.04em] text-panel-strong">
                  Verify to edit
                </h2>
                <p className="mt-1 text-sm text-panel-muted">
                  Enter the 6-digit code from your authenticator app.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIdentityModalOpen(false);
                }}
                className="inline-flex size-10 items-center justify-center rounded-full text-panel-muted transition hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_42%,transparent)] hover:text-panel-strong"
                aria-label="Close two-factor modal"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>

            {identityVerifyError ? <StatusBanner tone="danger" className="mt-5">{identityVerifyError}</StatusBanner> : null}

            <form className="mt-6 space-y-4" onSubmit={handleIdentityVerify}>
              <label className="block">
                <span className="text-sm font-semibold text-panel-copy">Authentication code</span>
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  maxLength={6}
                  value={identityCode}
                  onChange={(event) => {
                    const nextCode = event.target.value.replace(/\D/g, "").slice(0, 6);
                    setIdentityCode(nextCode);

                    if (nextCode.length < 6) {
                      lastIdentityVerificationCodeRef.current = null;
                    }

                    if (identityVerifyError) {
                      setIdentityVerifyError(null);
                    }
                  }}
                  className="mt-2 h-12 w-full rounded-[1rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-center text-lg font-semibold tracking-[0.2em] text-panel-strong outline-none focus:border-brand"
                  required
                />
              </label>

              <div className="flex flex-wrap justify-end gap-3 pt-2">
                <Button
                  variant="secondary"
                  onClick={() => {
                    setIdentityModalOpen(false);
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isVerifyingIdentity || identityCode.length !== 6}>
                  {isVerifyingIdentity ? "Verifying..." : "Verify"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
