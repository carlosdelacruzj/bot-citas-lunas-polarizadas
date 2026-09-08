import { HttpErrorResponse } from '@angular/common/http';

export function apiErrorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    if (error.status === 0) {
      return 'No se pudo conectar con la API local.';
    }
    const message =
      typeof error.error?.message === 'string' ? error.error.message : 'Respuesta no esperada.';
    const fieldErrors = error.error?.field_errors;
    if (fieldErrors && typeof fieldErrors === 'object') {
      const labels: Record<string, string> = {
        document_number: 'Usuario o documento',
        document_type: 'Tipo de documento',
        password: 'Contraseña',
        contact_name: 'Persona de contacto',
        contact_source: 'Fuente',
        contact_whatsapp: 'WhatsApp',
        message_template: 'Mensaje',
        expected_revision: 'Revisión',
      };
      const details = Object.entries(fieldErrors)
        .map(([field, value]) => `${labels[field] ?? field}: ${String(value)}`)
        .join(' ');
      return `${error.status} ${details || message}`;
    }
    return `${error.status} ${message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Error desconocido.';
}
