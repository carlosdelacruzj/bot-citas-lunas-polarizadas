import { HostedInvitation } from './appointment-api.service';

export interface RegistrationContinuityPreview {
  eyebrow: string;
  title: string;
  message: string;
}

const PREPARABLE_STATUSES = new Set([
  'submitted',
  'leased',
  'retry_wait',
  'accepted',
  'awaiting_restrictions',
  'credentials_invalid',
]);

export function canPrepareRegistrationContinuity(status: string): boolean {
  return PREPARABLE_STATUSES.has(status);
}

export function buildRegistrationContinuityPreview(
  invitation: HostedInvitation,
): RegistrationContinuityPreview | null {
  if (['submitted', 'leased', 'retry_wait'].includes(invitation.status)) {
    return {
      eyebrow: 'Recepción pendiente',
      title: 'Confirmar que recibimos el registro',
      message: [
        'Hola. Recibimos tu registro para el servicio de Citas Lunas Polarizadas.',
        '',
        'La validación está pendiente. Te avisaremos por este mismo WhatsApp cuando termine.',
        '',
        'Todavía no se ha iniciado el monitoreo ni se ha realizado ningún cobro.',
      ].join('\n'),
    };
  }

  if (invitation.status === 'accepted') {
    const availabilityLine =
      invitation.availability_mode === 'date_restrictions'
        ? 'Tal como coordinamos, intentaremos reservar la fecha más próxima disponible que respete tus restricciones.'
        : 'Tal como confirmaste, intentaremos reservar la fecha más próxima disponible.';
    return {
      eyebrow: 'Acceso validado',
      title: 'Continuar con el monitoreo',
      message: [
        'Hola. Continuamos por aquí con tu solicitud para conseguir una cita de lunas polarizadas.',
        '',
        'Ya validamos correctamente tu cuenta y comenzaremos con el monitoreo.',
        '',
        availabilityLine,
        '',
        'Te avisaremos por este medio apenas logremos reservar la cita y enviaremos la constancia correspondiente.',
        '',
        'El costo es de S/50 por cada trámite reservado y el pago se realiza únicamente después de confirmar cada cita.',
      ].join('\n'),
    };
  }

  if (invitation.status === 'awaiting_restrictions') {
    return {
      eyebrow: 'Faltan fechas',
      title: 'Coordinar restricciones antes de monitorear',
      message: [
        'Hola. Ya validamos correctamente tu cuenta.',
        '',
        'Antes de comenzar el monitoreo, indícanos qué fechas no puedes asistir.',
        '',
        'No activaremos la búsqueda hasta recibir tu respuesta y confirmar contigo esas fechas.',
      ].join('\n'),
    };
  }

  if (invitation.status === 'credentials_invalid') {
    return {
      eyebrow: 'Corrección necesaria',
      title: 'Informar que se necesita un enlace nuevo',
      message: [
        'Hola. No pudimos validar el acceso con los datos del registro.',
        '',
        'No envíes tu contraseña por este chat. Te enviaremos un enlace privado nuevo para que puedas corregirla de forma segura.',
        '',
        'El enlace anterior dejará de funcionar.',
      ].join('\n'),
    };
  }

  return null;
}
