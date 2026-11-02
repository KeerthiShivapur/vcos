/**
 * Frontend Hooks Index
 * Exports all custom React hooks for VCOS
 */

// Core hooks
export { useAuth } from "./useAuth";
export { useFetch } from "./useFetch";
export { useNotifications } from "./useNotifications";
export { useTheme } from "./useTheme";

// Real-time collaboration hooks
export { useRealtime, usePresence } from "./useRealtime";
export {
  useOfflineSync,
  useOfflineDocument,
  useOfflineDocuments,
  useOfflineNotifications,
} from "./useOfflineSync";
export {
  useCRDTDocument,
  useCRDTDocuments,
  useCRDTComments,
  useCRDTCursors,
} from "./useCRDT";
export {
  useCall,
  useIncomingCalls,
  useScreenShare,
  usePictureInPicture,
  useCallUI,
} from "./useCall";
export {
  useScreenShare,
  useCallScreenShare,
  useMeetingScreenShare,
  usePictureInPicture,
} from "./useScreenShare";
export {
  useComments,
  useAnnotations,
  useCommentPresence,
  useTypingIndicator,
} from "./useComments";
export { usePushNotifications, usePushSender } from "./usePushNotifications";
export {
  useE2EEncryption,
  useEncryptedCRDT,
  useE2EMessaging,
} from "./useE2EEncryption";

// Native/Mobile hooks
export { useNativeBridge, useNativePushNotifications } from "./useNativeBridge";
export {
  usePWAInstall,
  PWAInstallPrompt,
  PWAInstallBanner,
} from "@/components/pwa/PWAInstallPrompt";

// ML Platform hooks
export {
  useMLPlatform,
  useFeatureStore,
  useOnlineFeatures,
  useModelRegistry,
  useModelVersions,
  useInference,
  useCausalInference,
  useForecasting,
  useTextToSQL,
  useProactiveInsights,
} from "./useMLPlatform";

// Re-export ML Platform types
export type {
  Entity,
  Feature,
  FeatureView,
  OnlineFeatureRequest,
  OnlineReadRequest,
  ModelStage,
  ModelArtifact,
  ModelSignature,
  ModelVersion,
  RegisteredModel,
  ModelDeployment,
  InferenceBackend,
  InferenceRequest,
  InferenceResponse,
  CausalGraph,
  TreatmentEffect,
  CounterfactualResult,
  MediationAnalysis,
  ForecastMethod,
  TimeSeriesDataPoint,
  RegisterForecastDataRequest,
  ForecastRequest,
  ForecastResult,
  TextToSQLRequest,
  TextToSQLResponse,
  ValidateSQLRequest,
  ValidateSQLResponse,
  InsightType,
  InsightSeverity,
  DataPoint,
  TimeSeriesMetric,
  Anomaly,
  TrendChange,
  Insight,
  Alert,
  AlertRule,
} from "./useMLPlatform";

// Re-export types
export type {
  RealtimeMessage,
  PresenceData,
  UseRealtimeOptions,
} from "./useRealtime";
export type { OfflineSyncState, UseOfflineSyncOptions } from "./useOfflineSync";
export type {
  CRDTDocumentState,
  CRDTOperation,
  UseCRDTDocumentOptions,
} from "./useCRDT";
export type {
  CallParticipant,
  CallState,
  CallOptions,
  CallState as CallStateType,
} from "./useCall";
export type {
  ScreenShareOptions,
  ScreenShareState,
  UseScreenShareReturn,
} from "./useScreenShare";
export type {
  Comment,
  CommentThread,
  UseCommentsOptions,
  UseCommentsReturn,
} from "./useComments";
