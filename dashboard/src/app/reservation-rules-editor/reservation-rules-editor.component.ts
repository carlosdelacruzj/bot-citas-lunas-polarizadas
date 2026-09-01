import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { formatReservationDateRange } from '../reservation-rule-labels';
import { ExcludedDateRange } from '../reservation-rules.model';

type ReservationRulePreset = 'any' | 'saturdays' | 'from-date' | 'exclude-range' | 'date-window';

const WEEKDAYS = [
  { value: 1, short: 'L', label: 'Lunes' },
  { value: 2, short: 'M', label: 'Martes' },
  { value: 3, short: 'X', label: 'Miércoles' },
  { value: 4, short: 'J', label: 'Jueves' },
  { value: 5, short: 'V', label: 'Viernes' },
  { value: 6, short: 'S', label: 'Sábado' },
  { value: 7, short: 'D', label: 'Domingo' },
] as const;

@Component({
  selector: 'app-reservation-rules-editor',
  imports: [FormsModule],
  templateUrl: './reservation-rules-editor.component.html',
  styleUrl: './reservation-rules-editor.component.css',
})
export class ReservationRulesEditorComponent {
  @Input({ required: true }) controlPrefix = 'reservationRules';
  @Input() disabled = false;
  @Input() minimumDate = '';
  @Input() maximumDate = '';
  @Input() allowedWeekdays: number[] = [];
  @Input() excludedDateRanges: readonly ExcludedDateRange[] = [];
  @Input() excludedDateStart = '';
  @Input() excludedDateEnd = '';

  @Output() readonly minimumDateChange = new EventEmitter<string>();
  @Output() readonly maximumDateChange = new EventEmitter<string>();
  @Output() readonly allowedWeekdaysChange = new EventEmitter<number[]>();
  @Output() readonly excludedDateStartChange = new EventEmitter<string>();
  @Output() readonly excludedDateEndChange = new EventEmitter<string>();
  @Output() readonly addExcludedDateRange = new EventEmitter<void>();
  @Output() readonly removeExcludedDateRange = new EventEmitter<number>();
  @Output() readonly clearExcludedDateRanges = new EventEmitter<void>();

  protected readonly formatDateRange = formatReservationDateRange;
  protected readonly weekdays = WEEKDAYS;
  protected activePreset: ReservationRulePreset | null = null;

  protected toggleWeekday(day: number): void {
    if (this.disabled) {
      return;
    }
    const selected = new Set(this.allowedWeekdays);
    if (selected.has(day)) {
      selected.delete(day);
    } else {
      selected.add(day);
    }
    this.activePreset = null;
    this.allowedWeekdaysChange.emit([...selected].sort((left, right) => left - right));
  }

  protected isWeekdaySelected(day: number): boolean {
    return this.allowedWeekdays.includes(day);
  }

  protected applyPreset(preset: ReservationRulePreset): void {
    if (this.disabled) {
      return;
    }
    this.activePreset = preset;
    if (preset === 'any') {
      this.resetDateRules();
      return;
    }
    if (preset === 'saturdays') {
      this.resetDateRules([6]);
      return;
    }
    if (preset === 'from-date') {
      this.maximumDateChange.emit('');
      this.allowedWeekdaysChange.emit([]);
      this.clearExclusions();
      return;
    }
    if (preset === 'date-window') {
      this.allowedWeekdaysChange.emit([]);
      this.clearExclusions();
      return;
    }
    this.minimumDateChange.emit('');
    this.maximumDateChange.emit('');
    this.allowedWeekdaysChange.emit([]);
  }

  protected presetIsActive(preset: ReservationRulePreset): boolean {
    if (this.activePreset) {
      return this.activePreset === preset;
    }
    if (preset === 'any') {
      return (
        !this.minimumDate &&
        !this.maximumDate &&
        this.allowedWeekdays.length === 0 &&
        this.excludedDateRanges.length === 0 &&
        !this.excludedDateStart &&
        !this.excludedDateEnd
      );
    }
    return (
      preset === 'saturdays' &&
      this.allowedWeekdays.length === 1 &&
      this.allowedWeekdays[0] === 6 &&
      !this.minimumDate &&
      !this.maximumDate &&
      this.excludedDateRanges.length === 0
    );
  }

  private resetDateRules(allowedWeekdays: number[] = []): void {
    this.minimumDateChange.emit('');
    this.maximumDateChange.emit('');
    this.allowedWeekdaysChange.emit(allowedWeekdays);
    this.clearExclusions();
  }

  private clearExclusions(): void {
    this.excludedDateStartChange.emit('');
    this.excludedDateEndChange.emit('');
    if (this.excludedDateRanges.length > 0) {
      this.clearExcludedDateRanges.emit();
    }
  }
}
