import { ExcludedDateRange } from '../reservation-rules.model';
import { ServicePackageKey } from '../service-package.model';

export type ProgramResolutionChoice = '' | 'one' | 'all' | 'pause';
export type ProgramResolutionCommercialMode = '' | 'same_terms_per_program' | 'custom';
export type ProgramResolutionCommunicationDecision =
  | 'client_already_informed'
  | 'keep_without_send'
  | 'preview_single_confirmation';

export interface ProgramResolutionProgram {
  expediente: string | null;
  placa: string | null;
  status: string;
  [key: string]: unknown;
}

export interface ProgramResolutionPreflightDetails {
  error_type: 'multiple_pending_resolution_required';
  applicant_name?: string | null;
  program_count: number;
  pending_count: number;
  pending_programs: ProgramResolutionProgram[];
  listing_signature: string;
  listing_revision?: number;
}

export interface ProgramResolutionChildDraft {
  reservationPrice: string;
  chargeRequired: boolean;
}

export interface ProgramResolutionOrderTerms {
  reservation_price: string;
  charge_required: boolean;
  service_type: 'standard' | 'selected_weekday' | 'custom';
  service_package: ServicePackageKey;
  minimum_reservation_date: string | null;
  maximum_reservation_date: string | null;
  allowed_weekdays: number[] | null;
  excluded_date_ranges: ExcludedDateRange[];
}

export interface ProgramResolutionChildPayload {
  program_expediente: string;
  program_plate: string | null;
  reservation_price: string;
  charge_required: boolean;
  service_type: ProgramResolutionOrderTerms['service_type'];
  service_package: ProgramResolutionOrderTerms['service_package'];
  minimum_reservation_date: string | null;
  maximum_reservation_date: string | null;
  allowed_weekdays: number[] | null;
  excluded_date_ranges: ExcludedDateRange[];
}

export interface ProgramResolutionPayload {
  resolution: Exclude<ProgramResolutionChoice, ''>;
  listing_signature: string;
  program_expediente?: string;
  program_plate?: string | null;
  confirm_same_commercial_terms?: boolean;
  children?: ProgramResolutionChildPayload[];
  communication_decision: ProgramResolutionCommunicationDecision;
}

export interface ProgramResolutionResponse {
  status: string;
  message?: string;
  resolution: ProgramResolutionPayload['resolution'];
  parent_order_id: string;
  parent_archived: boolean;
  communication_decision: ProgramResolutionCommunicationDecision;
  communication_preview?: string | null;
  audit_id?: string | null;
  [key: string]: unknown;
}

export interface ProgramResolutionDraftInput {
  details: ProgramResolutionPreflightDetails | null;
  programs: ProgramResolutionProgram[];
  resolution: ProgramResolutionChoice;
  selectedExpediente: string;
  commercialMode: ProgramResolutionCommercialMode;
  sameTermsConfirmed: boolean;
  customInheritanceConfirmed: boolean;
  communicationDecision: '' | ProgramResolutionCommunicationDecision;
  children: Record<string, ProgramResolutionChildDraft>;
  order: ProgramResolutionOrderTerms;
}

export type ProgramResolutionBuildResult =
  | { ok: true; payload: ProgramResolutionPayload; confirmationLabel: string }
  | { ok: false; error: string };

export function programResolutionDetails(value: unknown): ProgramResolutionPreflightDetails | null {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const details = value as Record<string, unknown>;
  if (
    details['error_type'] !== 'multiple_pending_resolution_required' ||
    !Array.isArray(details['pending_programs']) ||
    typeof details['listing_signature'] !== 'string'
  ) {
    return null;
  }
  return details as unknown as ProgramResolutionPreflightDetails;
}

export function pendingResolutionPrograms(
  details: ProgramResolutionPreflightDetails | null,
): ProgramResolutionProgram[] {
  return (details?.pending_programs ?? []).filter(
    (program) => program.status.trim().toLocaleUpperCase('es') === 'PENDIENTE',
  );
}

export function defaultProgramResolutionChildren(
  programs: ProgramResolutionProgram[],
  order: ProgramResolutionOrderTerms,
  current: Record<string, ProgramResolutionChildDraft> = {},
): Record<string, ProgramResolutionChildDraft> {
  const children: Record<string, ProgramResolutionChildDraft> = {};
  for (const program of programs) {
    if (!program.expediente) {
      continue;
    }
    children[program.expediente] = current[program.expediente] ?? {
      reservationPrice: order.reservation_price,
      chargeRequired: order.charge_required,
    };
  }
  return children;
}

export function buildProgramResolution(
  input: ProgramResolutionDraftInput,
): ProgramResolutionBuildResult {
  const { details, programs, resolution, communicationDecision } = input;
  if (!details?.listing_signature) {
    return { ok: false, error: 'Actualiza el detalle: falta la revisión exacta del listado del portal.' };
  }
  if (programs.length === 0) {
    return { ok: false, error: 'No hay trámites PENDIENTE utilizables para resolver.' };
  }
  if (!resolution) {
    return { ok: false, error: 'Elige si resolver uno, resolver todos o mantener pausado.' };
  }
  if (!communicationDecision) {
    return { ok: false, error: 'Registra qué se decidió sobre la comunicación con el cliente.' };
  }
  const payload: ProgramResolutionPayload = {
    resolution,
    listing_signature: details.listing_signature,
    communication_decision: communicationDecision,
  };
  if (resolution === 'one') {
    const selected = programs.find(
      (program) => program.expediente === input.selectedExpediente,
    );
    if (!selected?.expediente) {
      return { ok: false, error: 'Selecciona un expediente PENDIENTE exacto.' };
    }
    payload.program_expediente = selected.expediente;
    payload.program_plate = selected.placa;
    return { ok: true, payload, confirmationLabel: `resolver solo ${selected.expediente}` };
  }
  if (resolution === 'pause') {
    return { ok: true, payload, confirmationLabel: 'mantener la orden pausada' };
  }
  if (!input.commercialMode) {
    return {
      ok: false,
      error: 'Elige cómo aplicar las condiciones comerciales a cada expediente.',
    };
  }
  if (input.commercialMode === 'same_terms_per_program') {
    if (!input.sameTermsConfirmed) {
      return {
        ok: false,
        error: 'Confirma expresamente que las mismas condiciones aplican a cada expediente.',
      };
    }
    payload.confirm_same_commercial_terms = true;
  } else {
    if (!input.customInheritanceConfirmed) {
      return {
        ok: false,
        error: 'Confirma que cada suborden heredará el servicio y las reglas visibles.',
      };
    }
    const children = buildChildrenPayload(programs, input.children, input.order);
    if (!children.ok) {
      return children;
    }
    payload.confirm_same_commercial_terms = false;
    payload.children = children.payload;
  }
  return {
    ok: true,
    payload,
    confirmationLabel: `crear ${programs.length} subórdenes y archivar el padre`,
  };
}

function buildChildrenPayload(
  programs: ProgramResolutionProgram[],
  drafts: Record<string, ProgramResolutionChildDraft>,
  order: ProgramResolutionOrderTerms,
): { ok: true; payload: ProgramResolutionChildPayload[] } | { ok: false; error: string } {
  const payload: ProgramResolutionChildPayload[] = [];
  for (const program of programs) {
    if (!program.expediente) {
      return {
        ok: false,
        error: 'El portal devolvió un trámite PENDIENTE sin expediente exacto; actualiza antes de continuar.',
      };
    }
    const draft = drafts[program.expediente];
    const price = Number(draft?.reservationPrice);
    if (!Number.isFinite(price) || price <= 0 || price > 99_999.99) {
      return { ok: false, error: `Ingresa un precio válido para ${program.expediente}.` };
    }
    payload.push({
      program_expediente: program.expediente,
      program_plate: program.placa,
      reservation_price: price.toFixed(2),
      charge_required: draft.chargeRequired,
      service_type: order.service_type,
      service_package: order.service_package,
      minimum_reservation_date: order.minimum_reservation_date,
      maximum_reservation_date: order.maximum_reservation_date,
      allowed_weekdays: order.allowed_weekdays,
      excluded_date_ranges: order.excluded_date_ranges,
    });
  }
  return { ok: true, payload };
}
