import { reportFromLogStep } from './qeosProgress';

export type StepLog = {
  step: string;
  status: 'pass' | 'fail' | 'info';
  durationMs?: number;
  detail?: string;
};

const logs: StepLog[] = [];

export function logStep(step: string, status: StepLog['status'], detail?: string, durationMs?: number) {
  const entry = { step, status, detail, durationMs };
  logs.push(entry);
  const prefix = status === 'pass' ? '✓' : status === 'fail' ? '✗' : '→';
  console.log(`${prefix} ${step}${detail ? ` — ${detail}` : ''}${durationMs != null ? ` (${durationMs}ms)` : ''}`);
  reportFromLogStep(step, status);
}

export function getExecutionLog(): StepLog[] {
  return [...logs];
}

export function clearLog() {
  logs.length = 0;
}
