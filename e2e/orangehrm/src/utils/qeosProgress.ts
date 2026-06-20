import fs from 'fs';
import type { Page } from '@playwright/test';

let stepIndex = 0;
let progressPage: Page | null = null;

export function resetQeosProgress() {
  stepIndex = 0;
  progressPage = null;
}

export function setQeosProgressPage(page: Page) {
  progressPage = page;
}

function totalSteps(): number {
  const n = parseInt(process.env.QEOS_TOTAL_STEPS || '15', 10);
  return Number.isFinite(n) && n > 0 ? n : 15;
}

function writeProgress(payload: Record<string, unknown>) {
  const file = process.env.QEOS_PROGRESS_FILE;
  if (!file) return;
  try {
    fs.writeFileSync(file, JSON.stringify({ ...payload, ts: Date.now() }));
  } catch {
    /* ignore */
  }
}

import { publishLiveFrame } from './helpers';

async function captureLiveFrame() {
  if (progressPage) {
    await publishLiveFrame(progressPage);
  }
}

/** Report step start — syncs Studio flow highlight with browser */
export function reportQeosStepStart(description: string) {
  writeProgress({
    step_index: Math.min(stepIndex, totalSteps() - 1),
    description,
    status: 'running',
  });
  void captureLiveFrame();
}

/** Report step completion and advance */
export function reportQeosStepDone(description: string, passed = true) {
  const idx = Math.min(stepIndex, totalSteps() - 1);
  writeProgress({
    step_index: idx,
    description,
    status: passed ? 'passed' : 'failed',
  });
  void captureLiveFrame();
  if (passed) {
    stepIndex = Math.min(stepIndex + 1, totalSteps() - 1);
  }
}

export async function captureLiveFrameNow() {
  await captureLiveFrame();
}

/** Hook for logger — maps log lines to live progress */
export function reportFromLogStep(step: string, status: 'pass' | 'fail' | 'info') {
  if (status === 'info') {
    reportQeosStepStart(step);
    return;
  }
  reportQeosStepDone(step, status === 'pass');
}
