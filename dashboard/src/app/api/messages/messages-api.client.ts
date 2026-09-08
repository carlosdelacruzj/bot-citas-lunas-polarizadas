import { Injectable, inject } from '@angular/core';
import type { RequestScope } from '../../request-cancellation';
import { ApiTransport } from '../shared/api-transport';
import type { ApiActionResponse } from '../shared/shared.contracts';
import type {
  WhatsAppFollowUpPackage,
  WhatsAppMessagePackage,
  WhatsAppMessageTemplate,
  WhatsAppMessageTemplatePreview,
  WhatsAppMessageTemplatesResponse,
  WhatsAppReviewPayload,
  WhatsAppReviewResolution,
  WhatsAppReviewResponse,
  WhatsAppWebDraftResponse,
} from './messages.contracts';

@Injectable({ providedIn: 'root' })
export class MessagesApiClient {
  private readonly transport = inject(ApiTransport);

  async getWhatsAppMessageTemplates(
    scope?: RequestScope,
  ): Promise<WhatsAppMessageTemplate[]> {
    const response = await this.transport.read<WhatsAppMessageTemplatesResponse>(
      '/api/v1/whatsapp-message-templates',
      scope,
    );
    return response.templates;
  }

  async previewWhatsAppMessageTemplate(
    templateKey: string,
    messageTemplate: string,
  ): Promise<WhatsAppMessageTemplatePreview> {
    return this.transport.post<WhatsAppMessageTemplatePreview>(
      `/api/v1/whatsapp-message-templates/${encodeURIComponent(templateKey)}/preview`,
      { message_template: messageTemplate },
    );
  }

  async updateWhatsAppMessageTemplate(
    templateKey: string,
    messageTemplate: string,
    expectedRevision: number,
  ): Promise<WhatsAppMessageTemplate> {
    return this.transport.put<WhatsAppMessageTemplate>(
      `/api/v1/whatsapp-message-templates/${encodeURIComponent(templateKey)}`,
      {
        message_template: messageTemplate,
        expected_revision: expectedRevision,
      },
    );
  }

  async prepareWhatsAppTest(recipientPhone: string): Promise<WhatsAppMessagePackage> {
    return this.transport.post<WhatsAppMessagePackage>('/api/v1/whatsapp-messages/test/prepare', {
      recipient_phone: recipientPhone,
    });
  }

  async prepareWhatsAppFollowUpTest(recipientPhone: string): Promise<WhatsAppFollowUpPackage> {
    return this.transport.post<WhatsAppFollowUpPackage>('/api/v1/whatsapp-followup-messages/test/prepare', {
      recipient_phone: recipientPhone,
    });
  }

  async prepareOrderWhatsApp(
    orderId: string,
    allowResend = false,
  ): Promise<WhatsAppMessagePackage> {
    return this.transport.post<WhatsAppMessagePackage>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/whatsapp/prepare`,
      { allow_resend: allowResend },
    );
  }

  async preparePostPaymentWhatsApp(
    orderId: string,
    allowResend = false,
  ): Promise<WhatsAppFollowUpPackage> {
    return this.transport.post<WhatsAppFollowUpPackage>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/whatsapp-followup/prepare`,
      { allow_resend: allowResend },
    );
  }

  async getWhatsAppReview(
    orderId: string,
    kind: 'whatsapp' | 'whatsapp-followup',
  ): Promise<WhatsAppReviewPayload> {
    return this.transport.read<WhatsAppReviewPayload>(
      `/api/v1/service-orders/${encodeURIComponent(orderId)}/${encodeURIComponent(kind)}/review`,
    );
  }

  async resolveWhatsAppReview(
    jobKey: string,
    resolution: WhatsAppReviewResolution,
    note: string | null,
  ): Promise<WhatsAppReviewResponse> {
    return this.transport.post<WhatsAppReviewResponse>(
      `/api/v1/whatsapp-automation-jobs/${encodeURIComponent(jobKey)}/resolve`,
      { resolution, note },
    );
  }

  async markWhatsAppSent(messageId: string): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/whatsapp-messages/${encodeURIComponent(messageId)}/sent`,
      {},
    );
  }

  async markWhatsAppFollowUpSent(messageId: string): Promise<ApiActionResponse> {
    return this.transport.post<ApiActionResponse>(
      `/api/v1/whatsapp-followup-messages/${encodeURIComponent(messageId)}/sent`,
      {},
    );
  }

  async prepareWhatsAppFollowUpWebDraft(messageId: string): Promise<WhatsAppWebDraftResponse> {
    return this.transport.post<WhatsAppWebDraftResponse>(
      `/api/v1/whatsapp-followup-messages/${encodeURIComponent(messageId)}/web/prepare`,
      {},
    );
  }

  async validateWhatsAppWebSession(): Promise<WhatsAppWebDraftResponse> {
    return this.transport.post<WhatsAppWebDraftResponse>('/api/v1/whatsapp-web/session/validate', {});
  }

  async prepareWhatsAppWebDraft(
    messageId: string,
    draftKind: 'confirmation' | 'payment' | 'album',
    autoSend = false,
  ): Promise<WhatsAppWebDraftResponse> {
    return this.transport.post<WhatsAppWebDraftResponse>(
      `/api/v1/whatsapp-messages/${encodeURIComponent(messageId)}/web/prepare`,
      { draft_kind: draftKind, auto_send: autoSend },
    );
  }

  async getWhatsAppAttachment(url: string): Promise<Blob> {
    return this.transport.blob(url);
  }
}
