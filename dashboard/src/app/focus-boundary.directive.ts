import { Directive, ElementRef, HostListener, OnDestroy, effect, inject, input } from '@angular/core';

const FOCUSABLE = 'button, a[href], input, select, textarea, [tabindex]';

@Directive({ selector: '[appFocusBoundary]' })
export class FocusBoundaryDirective implements OnDestroy {
  readonly enabled = input(true, { alias: 'appFocusBoundary' });
  private readonly host: HTMLElement = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private previousFocus: HTMLElement | null = null;
  private activated = false;
  private release: (() => void) | null = null;

  constructor() {
    effect((onCleanup) => {
      if (!this.enabled()) { this.activated = false; return; }
      if (!this.activated) {
        this.previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        this.activated = true;
      }
      const inertElements: [HTMLElement, boolean][] = [];
      let branch: HTMLElement = this.host;
      while (branch.parentElement && branch !== document.body) {
        for (const sibling of Array.from(branch.parentElement.children)) {
          if (sibling instanceof HTMLElement && sibling !== branch && !['SCRIPT', 'STYLE'].includes(sibling.tagName)) {
            inertElements.push([sibling, sibling.inert]);
            sibling.inert = true;
          }
        }
        branch = branch.parentElement;
      }
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      const timer = window.setTimeout(() => {
        if (!this.enabled() || !this.host.isConnected || this.host.contains(document.activeElement)) return;
        this.host.querySelector<HTMLElement>('[data-modal-initial-focus]')?.focus();
        if (!this.host.contains(document.activeElement)) (this.focusable()[0] ?? this.host).focus();
      });
      this.release = () => {
        window.clearTimeout(timer);
        for (const [element, wasInert] of inertElements) element.inert = wasInert;
        document.body.style.overflow = previousOverflow;
        this.release = null;
        const target = this.previousFocus;
        window.setTimeout(() => {
          if (!this.enabled() && this.host.contains(document.activeElement) && target?.isConnected && !target.closest('[inert]')) target.focus({ preventScroll: true });
        });
      };
      onCleanup(this.release);
    });
  }

  private focusable(): HTMLElement[] {
    return Array.from(this.host.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(element =>
      element.tabIndex >= 0 && !element.matches(':disabled') && !element.closest('[inert]') && element.getClientRects().length > 0,
    );
  }

  @HostListener('document:keydown', ['$event'])
  handleKey(event: KeyboardEvent): void {
    if (!this.enabled() || event.key !== 'Tab' || document.querySelector('.swal2-container')) return;
    const items = this.focusable();
    const first = items[0] ?? this.host;
    const last = items.at(-1) ?? this.host;
    if (!this.host.contains(document.activeElement) || (event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last) || !items.length) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    }
  }

  ngOnDestroy(): void {
    this.release?.();
    const target = this.previousFocus;
    window.setTimeout(() => {
      if (target?.isConnected && !target.closest('[inert]') && (document.activeElement === document.body || !document.activeElement?.isConnected)) target.focus({ preventScroll: true });
    });
  }
}
