// Thin typed API client — specs/03-design/10-frontend-pages.md.
// Every backend call goes through here so the transport (base URL, auth
// headers once task-14 lands) changes in one place.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface FfmpegStatus {
  present: boolean;
  version: string | null;
}

export interface HealthStatus {
  ffmpeg: FfmpegStatus;
  subtitle_filters_available: boolean;
  cuda_available: boolean;
  keys_configured: {
    gemini: boolean;
    pexels: boolean;
    pixabay: boolean;
  };
  db_migrated: boolean;
  schema_version: number;
}

export type VoiceTable = Record<string, { female: string; male: string }>;

export type Language = "hi" | "en";
export type DurationS = 30 | 60 | 120 | 300;
export type VideoFormat = "9x16" | "16x9";

export interface Project {
  id: string;
  user_id: string;
  title: string | null;
  description: string;
  language: Language;
  duration_s: DurationS;
  format: VideoFormat;
  status: string;
  mode: string | null;
  voice: string | null;
  accepted_version_id: string | null;
  output_path: string | null;
  created_at: string;
  // Present on GET /api/projects/{id}; null on the bare POST response.
  latest_script_version: ScriptVersion | null;
}

export interface Scene {
  id: number;
  text: string;
  visual_hint: string;
  visual_hint_stale: boolean;
}

export type ScriptOrigin = "generated" | "improved" | "edited" | "cloned";

export interface ScriptVersion {
  id: string;
  project_id: string;
  n: number;
  scenes: Scene[];
  origin: ScriptOrigin;
  created_at: string;
}

export interface ScriptVersionSummary {
  id: string;
  n: number;
  origin: ScriptOrigin;
  created_at: string;
}

interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    hint?: string;
  };
}

export class ApiRequestError extends Error {
  code: string;
  hint?: string;
  status: number;

  constructor(code: string, message: string, hint: string | undefined, status: number) {
    super(message);
    this.code = code;
    this.hint = hint;
    this.status = status;
  }
}

async function handleResponse<T>(res: Response, path: string): Promise<T> {
  if (!res.ok) {
    // Session missing/expired - redirect-when-unauthenticated
    // (specs/04-tasks/task-14-auth-accounts.md). A full page redirect
    // rather than router.push(): this fires from plain async functions,
    // not React components, so there's no router instance available here.
    if (res.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }

    const payload = (await res.json().catch(() => null)) as ApiErrorBody | null;
    if (payload?.error) {
      throw new ApiRequestError(
        payload.error.code,
        payload.error.message,
        payload.error.hint,
        res.status
      );
    }
    throw new ApiRequestError("unknown_error", `${path} responded ${res.status}`, undefined, res.status);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

// credentials: "include" on every call - task-14's session cookie is set
// by the backend (a different origin in dev, :8000 vs :3000), and
// cross-origin fetch defaults to NOT sending/receiving cookies without
// this. CORS's allow_credentials=True on the backend is the other half.
async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store", credentials: "include" });
  return handleResponse<T>(res, path);
}

async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(res, path);
}

async function apiPostForm<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  return handleResponse<T>(res, path);
}

async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse<T>(res, path);
}

async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { method: "DELETE", credentials: "include" });
  return handleResponse<T>(res, path);
}

export function getHealth(): Promise<HealthStatus> {
  return apiGet<HealthStatus>("/api/meta/health");
}

export interface TierState {
  worker_online: boolean;
  zerogpu_seconds_remaining: number;
  sadtalker_configured: boolean;
  active_tier: "worker" | "zerogpu" | "cpu";
  label: string;
}

export function getTierState(): Promise<TierState> {
  return apiGet<TierState>("/api/meta/tier");
}

export interface User {
  id: string;
  email: string;
  role: string;
  created_at: string;
}

export function login(email: string, password: string): Promise<User> {
  return apiPost<User>("/api/auth/login", { email, password });
}

export function logout(): Promise<void> {
  return apiPost<void>("/api/auth/logout");
}

export function getMe(): Promise<User> {
  return apiGet<User>("/api/me");
}

export function deleteAccount(): Promise<void> {
  return apiDelete<void>("/api/me");
}

export function getVoices(): Promise<VoiceTable> {
  return apiGet<VoiceTable>("/api/meta/voices");
}

export type MusicMood = "calm" | "upbeat" | "mystical" | "corporate";

export function getMusicMoods(): Promise<MusicMood[]> {
  return apiGet<MusicMood[]>("/api/meta/music/moods");
}

export function musicPreviewUrl(mood: MusicMood): string {
  return `${API_BASE_URL}/api/meta/music/preview/${mood}`;
}

export function createProject(input: {
  description: string;
  language: Language;
  duration_s: DurationS;
  format: VideoFormat;
}): Promise<Project> {
  return apiPost<Project>("/api/projects", input);
}

export function getProject(id: string): Promise<Project> {
  return apiGet<Project>(`/api/projects/${id}`);
}

export interface ProjectSummary {
  id: string;
  title: string | null;
  language: Language;
  format: VideoFormat;
  duration_s: number;
  mode: string | null;
  status: string;
  has_thumbnail: boolean;
  active_job_id: string | null;
  created_at: string;
}

export function listProjects(): Promise<ProjectSummary[]> {
  return apiGet<ProjectSummary[]>("/api/projects");
}

export function deleteProject(id: string): Promise<void> {
  return apiDelete<void>(`/api/projects/${id}`);
}

export function projectThumbnailUrl(id: string): string {
  return `${API_BASE_URL}/api/projects/${id}/thumbnail`;
}

export function generateScript(projectId: string): Promise<ScriptVersion> {
  return apiPost<ScriptVersion>(`/api/projects/${projectId}/script`);
}

export function listScriptVersions(projectId: string): Promise<ScriptVersionSummary[]> {
  return apiGet<ScriptVersionSummary[]>(`/api/projects/${projectId}/script/versions`);
}

export function editScene(
  projectId: string,
  sceneId: number,
  text: string
): Promise<ScriptVersion> {
  return apiPut<ScriptVersion>(`/api/projects/${projectId}/script/scene/${sceneId}`, { text });
}

export function restoreVersion(projectId: string, versionId: string): Promise<ScriptVersion> {
  return apiPost<ScriptVersion>(`/api/projects/${projectId}/script/restore/${versionId}`);
}

export function acceptScript(projectId: string): Promise<Project> {
  return apiPost<Project>(`/api/projects/${projectId}/script/accept`);
}

export function scrapScript(projectId: string): Promise<Project> {
  return apiDelete<Project>(`/api/projects/${projectId}/script`);
}

export function estimateDurationS(scenes: Scene[], language: Language): number {
  const wordsPerMinute = language === "hi" ? 120 : 140;
  const wordCount = scenes.reduce((sum, s) => sum + s.text.trim().split(/\s+/).filter(Boolean).length, 0);
  return (wordCount / wordsPerMinute) * 60;
}

export interface ImproveProposal {
  scene_id: number;
  old_span: string;
  new_span: string;
  proposed_scene_text: string;
}

// DOM selection offsets (textarea.selectionStart/End) are UTF-16 code unit
// offsets; the backend indexes scene text by Unicode codepoint. These are
// identical for this product's actual content (Devanagari/Latin/digits are
// all within the BMP) but we convert properly anyway, per
// specs/04-tasks/task-04-improve-selection.md's explicit "use codepoint
// offsets, not UTF-16 indices, on the wire".
export function utf16OffsetToCodepointOffset(text: string, utf16Offset: number): number {
  return [...text.slice(0, utf16Offset)].length;
}

export function improveSelection(
  projectId: string,
  input: {
    version_id: string;
    scene_id: number;
    start: number;
    end: number;
    instruction?: string;
  }
): Promise<ImproveProposal> {
  return apiPost<ImproveProposal>(`/api/projects/${projectId}/script/improve`, input);
}

export function applyImprovement(
  projectId: string,
  input: { scene_id: number; proposed_scene_text: string }
): Promise<ScriptVersion> {
  return apiPost<ScriptVersion>(`/api/projects/${projectId}/script/apply`, input);
}

export type JobStatus = "queued" | "running" | "awaiting_user" | "done" | "failed" | "cancelled";

export interface Job {
  id: string;
  type: string;
  status: JobStatus;
  stage: string | null;
  stages: string[];
  progress: number;
  error: string | null;
  queue_position: number | null;
}

export function createDebugNoopJob(): Promise<Job> {
  return apiPost<Job>("/api/jobs/debug/noop");
}

export function getJob(jobId: string): Promise<Job> {
  return apiGet<Job>(`/api/jobs/${jobId}`);
}

export function cancelJob(jobId: string): Promise<Job> {
  return apiPost<Job>(`/api/jobs/${jobId}/cancel`);
}

export type SubtitleStyle = "phrase" | "karaoke";

export function createRenderJob(
  projectId: string,
  input: {
    mode: "a" | "b";
    avatar_id?: string;
    voice_profile_id?: string;
    subtitles?: boolean;
    subtitle_style?: SubtitleStyle;
    hd_requested?: boolean;
    music_enabled?: boolean;
    music_mood?: MusicMood;
  }
): Promise<Job> {
  return apiPost<Job>(`/api/projects/${projectId}/video`, input);
}

export function voicePreviewUrl(voiceId: string): string {
  return `${API_BASE_URL}/api/meta/voices/${voiceId}/preview`;
}

export function videoStreamUrl(projectId: string): string {
  return `${API_BASE_URL}/api/projects/${projectId}/video`;
}

export function videoDownloadUrl(projectId: string): string {
  return `${API_BASE_URL}/api/projects/${projectId}/video/download`;
}

export function sceneImageUrl(projectId: string, sceneId: number): string {
  return `${API_BASE_URL}/api/projects/${projectId}/scenes/${sceneId}/image`;
}

export interface ImageCandidate {
  source: string;
  source_id: string;
  width: number | null;
  height: number | null;
  url: string | null;
  photographer: string | null;
  photographer_url: string | null;
}

export interface SceneCandidates {
  current: ImageCandidate;
  alternates: ImageCandidate[];
  can_generate_new: boolean;
}

export function getSceneCandidates(projectId: string, sceneId: number): Promise<SceneCandidates> {
  return apiGet<SceneCandidates>(`/api/projects/${projectId}/scenes/${sceneId}/candidates`);
}

export function swapSceneImage(
  projectId: string,
  sceneId: number,
  input: { source_id?: string; generate_new?: boolean }
): Promise<Job> {
  return apiPost<Job>(`/api/projects/${projectId}/scenes/${sceneId}/image`, input);
}

export function rerenderScene(
  projectId: string,
  sceneId: number,
  input: { voice?: string }
): Promise<Job> {
  return apiPost<Job>(`/api/projects/${projectId}/scenes/${sceneId}/rerender`, input);
}

export interface RerenderOtherModeResult {
  project_id: string;
  job: Job;
}

export function rerenderOtherMode(
  projectId: string,
  input: { avatar_id?: string }
): Promise<RerenderOtherModeResult> {
  return apiPost<RerenderOtherModeResult>(`/api/projects/${projectId}/rerender`, input);
}

export interface Avatar {
  id: string;
  user_id: string;
  name: string | null;
  persona_description: string | null;
  selfie_path: string | null;
  portrait_path: string | null;
  approved: boolean;
  consented: boolean;
  created_at: string;
}

export interface AvatarWithJob extends Avatar {
  job_id: string;
}

export function createAvatar(input: {
  selfie: File;
  persona_description: string;
  name: string;
  consent: boolean;
}): Promise<AvatarWithJob> {
  const form = new FormData();
  form.set("selfie", input.selfie);
  form.set("persona_description", input.persona_description);
  form.set("name", input.name);
  form.set("consent", String(input.consent));
  return apiPostForm<AvatarWithJob>("/api/avatars", form);
}

export function listApprovedAvatars(): Promise<Avatar[]> {
  return apiGet<Avatar[]>("/api/avatars");
}

export function getAvatar(avatarId: string): Promise<Avatar> {
  return apiGet<Avatar>(`/api/avatars/${avatarId}`);
}

export function approveAvatar(avatarId: string): Promise<Avatar> {
  return apiPost<Avatar>(`/api/avatars/${avatarId}/approve`);
}

export function restyleAvatar(avatarId: string, personaDescription: string): Promise<AvatarWithJob> {
  return apiPost<AvatarWithJob>(`/api/avatars/${avatarId}/restyle`, {
    persona_description: personaDescription,
  });
}

export function deleteAvatar(avatarId: string): Promise<void> {
  return apiDelete<void>(`/api/avatars/${avatarId}`);
}

export function deleteAvatarSelfie(avatarId: string): Promise<Avatar> {
  return apiDelete<Avatar>(`/api/avatars/${avatarId}/selfie`);
}

export function avatarSelfieUrl(avatarId: string): string {
  return `${API_BASE_URL}/api/avatars/${avatarId}/selfie`;
}

export function avatarPortraitUrl(avatarId: string): string {
  return `${API_BASE_URL}/api/avatars/${avatarId}/portrait`;
}

// --- Personal voice (task-18) -----------------------------------------

export interface VoiceProfile {
  id: string;
  user_id: string;
  kind: "cloned" | "designed";
  description: string | null;
  base_voice: string | null;
  consented: boolean;
  created_at: string;
}

export function listVoiceProfiles(): Promise<VoiceProfile[]> {
  return apiGet<VoiceProfile[]>("/api/voices");
}

export function getVoicePassage(language: string): Promise<{ language: string; text: string }> {
  return apiGet<{ language: string; text: string }>(`/api/voices/passage/${language}`);
}

export function enrollVoice(input: {
  sample: Blob;
  language: string;
  consent: boolean;
  base_voice?: string;
}): Promise<VoiceProfile> {
  const form = new FormData();
  form.set("sample", input.sample, "sample.webm");
  form.set("language", input.language);
  form.set("consent", String(input.consent));
  if (input.base_voice) form.set("base_voice", input.base_voice);
  return apiPostForm<VoiceProfile>("/api/voices/enroll", form);
}

export function deleteVoiceProfile(profileId: string): Promise<void> {
  return apiDelete<void>(`/api/voices/${profileId}`);
}

export function voicePreviewUrlForProfile(profileId: string): string {
  return `${API_BASE_URL}/api/voices/${profileId}/preview`;
}
