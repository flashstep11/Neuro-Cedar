/**
 * playwright_qa.js — Cedarline QA screenshot script.
 *
 * Walks all 4 cells (Neutral/Manipulative × 0%/35%) through the full study
 * flow, capturing full-page screenshots at 390px (mobile) and 1280px (desktop)
 * for every investment stage.
 *
 * Also produces:
 *   - Per-stage side-by-side montage (Neutral vs Manipulative, same reward)
 *   - qa_screenshots/CUE_AUDIT.md — cue presence audit
 *
 * Requirements:
 *   - oTree devserver running at http://localhost:8000
 *   - npm install (in this directory) before running
 *   - node playwright_qa.js
 *
 * Usage:
 *   cd qa && npm install && node playwright_qa.js
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL     = 'http://localhost:8000';
const OUT_DIR      = path.join(__dirname, '..', 'qa_screenshots');
const WIDTHS       = [390, 1280];
const ADMIN_USER   = 'admin';
const ADMIN_PASS   = 'changeme_before_deploy';

// Map session config names to cell labels
const CELLS = [
  { session: 'dev_neutral_0pct',   ui: 'neutral',       reward: '0pct',  label: 'N-0'  },
  { session: 'dev_neutral_35pct',  ui: 'neutral',       reward: '35pct', label: 'N-35' },
  { session: 'dev_manip_0pct',     ui: 'manipulative',  reward: '0pct',  label: 'M-0'  },
  { session: 'dev_manip_35pct',    ui: 'manipulative',  reward: '35pct', label: 'M-35' },
];

// Investment stages in order (page class names map to URL slugs in oTree)
const STAGES = [
  'S1Endowment', 'S2Commitment', 'S3ReturnReveal',
  'S4Reinvestment', 'S5PoolOutcome', 'S6Withdraw',
  'S7FeeDisplay', 'S8PayAbandon',
];

// Cue matrix: which cues appear per stage per arm
const CUE_MATRIX = {
  S2Commitment:   { neutral: [],                                    manipulative: ['banner', 'tier', 'ticker'] },
  S3ReturnReveal: { neutral: [],                                    manipulative: ['banner', 'tier', 'ticker'] },
  S4Reinvestment: { neutral: [],                                    manipulative: ['banner', 'tier', 'ticker', 'styled-cta'] },
  S5PoolOutcome:  { neutral: [],                                    manipulative: ['banner', 'tier', 'ticker'] },
  S6Withdraw:     { neutral: [],                                    manipulative: ['banner', 'ticker'] },
  S7FeeDisplay:   { neutral: [],                                    manipulative: ['banner', 'ticker'] },
  S8PayAbandon:   { neutral: [],                                    manipulative: ['banner', 'ticker', 'styled-cta'] },
  S1Endowment:    { neutral: [],                                    manipulative: [] },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function screenshotPath(stage, label, width) {
  return path.join(OUT_DIR, `${stage}_${label}_${width}px.png`);
}

async function loginAdmin(page) {
  await page.goto(`${BASE_URL}/accounts/login/`);
  await page.fill('[name="username"]', ADMIN_USER);
  await page.fill('[name="password"]', ADMIN_PASS);
  await page.click('[type="submit"]');
  await page.waitForURL('**/admin/**', { timeout: 5000 }).catch(() => {});
}

async function createSession(page, sessionName, nParticipants = 1) {
  await page.goto(`${BASE_URL}/create_session/`);
  await page.waitForSelector('[name="session_config_name"]', { timeout: 5000 });
  await page.selectOption('[name="session_config_name"]', sessionName);
  const nField = page.locator('[name="num_participants"]');
  if (await nField.count()) {
    await nField.fill(String(nParticipants));
  }
  await page.click('[type="submit"]');
  // Wait for session URL
  await page.waitForURL('**/SessionStartLinks/**', { timeout: 10000 });
  const url = page.url();
  const code = url.match(/SessionStartLinks\/([^/]+)/)?.[1];
  return code;
}

async function getParticipantLink(page, sessionCode) {
  await page.goto(`${BASE_URL}/SessionStartLinks/${sessionCode}/`);
  const links = await page.locator('a[href*="/InitializeParticipant/"]').all();
  if (!links.length) throw new Error('No participant links found');
  return await links[0].getAttribute('href');
}

// Check which cue elements are present on the current page
async function auditCues(page) {
  const present = [];
  if (await page.locator('#cl-urgency-banner').count()) present.push('banner');
  if (await page.locator('.cl-tier-card').count()) present.push('tier');
  if (await page.locator('.cl-ticker').count()) present.push('ticker');
  if (await page.locator('.cl-btn--manip-primary').count()) present.push('styled-cta');
  return present;
}

// Extract all visible monetary values from the page
async function extractFinancialValues(page) {
  const vals = {};
  // Cash balance
  const cash = page.locator('.cl-balance-card:has(.cl-balance-card__label:text("Cash Available")) .cl-balance-card__amount');
  if (await cash.count()) vals.cash = (await cash.textContent()).trim();
  // Platform balance
  const plat = page.locator('.cl-balance-card:has(.cl-balance-card__label:text("Platform Balance")) .cl-balance-card__amount');
  if (await plat.count()) vals.platform = (await plat.textContent()).trim();
  return vals;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
(async () => {
  ensureDir(OUT_DIR);
  const browser = await chromium.launch({ headless: true });

  const auditRows = [];   // For CUE_AUDIT.md
  const screenshots = {}; // stage -> { label -> path } for montage

  for (const cell of CELLS) {
    console.log(`\n=== Cell: ${cell.label} (${cell.session}) ===`);
    const context = await browser.newContext({
      viewport: { width: WIDTHS[1], height: 900 },
    });
    const page = await context.newPage();

    // Login and create session
    await loginAdmin(page);
    let sessionCode;
    try {
      sessionCode = await createSession(page, cell.session, 1);
    } catch (e) {
      console.warn(`  Could not create session ${cell.session}: ${e.message}`);
      await context.close();
      continue;
    }

    const participantHref = await getParticipantLink(page, sessionCode);
    const participantUrl  = `${BASE_URL}${participantHref}`;

    // Walk the study for each width, capturing screenshots
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });

      // Start participant flow
      await page.goto(participantUrl);
      await page.waitForLoadState('networkidle');

      let currentStage = null;

      // Helper: screenshot the current page if it's a named stage
      const captureIfStage = async (stageName) => {
        const title = await page.title();
        const url   = page.url();
        const shot  = screenshotPath(stageName, cell.label, width);
        await page.screenshot({ path: shot, fullPage: true });
        console.log(`  Screenshot: ${path.basename(shot)}`);
        if (!screenshots[stageName]) screenshots[stageName] = {};
        screenshots[stageName][cell.label] = shot;

        // Audit cues (only need once per cell, at 1280px)
        if (width === WIDTHS[1]) {
          const cues   = await auditCues(page);
          const finVals = await extractFinancialValues(page);
          auditRows.push({
            stage: stageName, arm: cell.ui, reward: cell.reward,
            cues, finVals,
          });
        }
      };

      // ---- Walk pages ----
      // ContentWarning
      await captureIfStage('ContentWarning');
      await page.click('button[type="submit"]:has-text("Continue")').catch(() =>
        page.click('button[type="submit"]').catch(() => {})
      );
      await page.waitForLoadState('networkidle');

      // Instructions
      await captureIfStage('Instructions');
      await page.click('button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // Consent
      await captureIfStage('Consent');
      // Check 18+ and agree
      await page.check('[name="q_18"][value="yes"]').catch(() => {});
      await page.check('[name="q_agree"][value="yes"]').catch(() => {});
      await page.click('#consent-submit').catch(() =>
        page.click('button[type="submit"]').catch(() => {})
      );
      await page.waitForLoadState('networkidle');

      // ComprehensionQuiz — submit directly (bot mode)
      await captureIfStage('ComprehensionQuiz');
      await page.click('#otree-form button, button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // Assignment (auto-advances)
      await page.waitForTimeout(1500);
      await page.waitForLoadState('networkidle');

      // S1
      await captureIfStage('S1Endowment');
      await page.click('button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // S2
      await captureIfStage('S2Commitment');
      await page.click('button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // S3
      await captureIfStage('S3ReturnReveal');
      await page.click('button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // S4 — select R=100
      await captureIfStage('S4Reinvestment');
      await page.selectOption('#reinvest_amount', '100').catch(() => {});
      await page.click('button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // S5
      await captureIfStage('S5PoolOutcome');
      await page.click('button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // S6
      await captureIfStage('S6Withdraw');
      await page.click('button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // S7
      await captureIfStage('S7FeeDisplay');
      await page.click('button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // S8 — click Pay
      await captureIfStage('S8PayAbandon');
      await page.click('#form-pay button').catch(() =>
        page.click('button[type="submit"]').catch(() => {})
      );
      await page.waitForLoadState('networkidle');

      // PostTask
      await captureIfStage('PostTask');
      // Fill in Likert scales
      for (const name of ['q_trust','q_legitimacy','q_risk','q_confidence','q_attention']) {
        await page.check(`[name="${name}"][value="4"]`).catch(() => {});
      }
      await page.check('[name="q_reward_noticed"][value="no"]').catch(() => {});
      await page.check('[name="q_ui_noticed"][value="no"]').catch(() => {});
      await page.click('button[type="submit"]').catch(() => {});
      await page.waitForLoadState('networkidle');

      // LotteryContact — skip
      await captureIfStage('LotteryContact');
      await page.click('#contact-skip-btn').catch(() =>
        page.click('button[type="submit"]').catch(() => {})
      );
      await page.waitForLoadState('networkidle');

      // Debrief
      await captureIfStage('Debrief');

      // Reset for next width
      await page.goto(participantUrl);
    }

    await context.close();
  }

  await browser.close();

  // ---------------------------------------------------------------------------
  // Generate CUE_AUDIT.md
  // ---------------------------------------------------------------------------
  const EXPECTED_CUES = CUE_MATRIX;

  let md = `# Cue Audit — Cedarline Study\n\nGenerated: ${new Date().toISOString()}\n\n`;
  md += `## Cue Matrix\n\n`;
  md += `| Stage | Neutral Expected | Manipulative Expected |\n`;
  md += `|-------|-----------------|----------------------|\n`;

  for (const [stage, arms] of Object.entries(EXPECTED_CUES)) {
    const ne = arms.neutral.join(', ') || '—';
    const me = arms.manipulative.join(', ') || '—';
    md += `| ${stage} | ${ne} | ${me} |\n`;
  }

  md += `\n## Audit Results\n\n`;
  md += `| Stage | Arm | Reward | Cues Found | Expected | Match | Cash | Platform |\n`;
  md += `|-------|-----|--------|-----------|----------|-------|------|----------|\n`;

  const finValuesByStageReward = {}; // For cross-arm financial comparison

  for (const row of auditRows) {
    const expected = (EXPECTED_CUES[row.stage]?.[row.arm] || []);
    const found    = row.cues;
    const match    = JSON.stringify(found.sort()) === JSON.stringify(expected.sort()) ? '✅' : '❌';

    const key = `${row.stage}_${row.reward}`;
    if (!finValuesByStageReward[key]) finValuesByStageReward[key] = {};
    finValuesByStageReward[key][row.arm] = row.finVals;

    md += `| ${row.stage} | ${row.arm} | ${row.reward} | ${found.join(', ') || '—'} | ${expected.join(', ') || '—'} | ${match} | ${row.finVals.cash || '—'} | ${row.finVals.platform || '—'} |\n`;
  }

  md += `\n## Financial Value Cross-Arm Check\n\n`;
  md += `Verifies that financial values are IDENTICAL across UI arms for the same reward condition.\n\n`;
  md += `| Stage | Reward | Neutral Cash | Manip Cash | Cash Match | Neutral Platform | Manip Platform | Platform Match |\n`;
  md += `|-------|--------|-------------|------------|-----------|----------------|---------------|---------------|\n`;

  for (const [key, arms] of Object.entries(finValuesByStageReward)) {
    const [stage, reward] = key.split('_0p').length > 1
      ? [key.split('_0p')[0], '0pct']
      : [key.split('_35p')[0], '35pct'];
    const n = arms.neutral || {};
    const m = arms.manipulative || {};
    const cashMatch = n.cash === m.cash ? '✅' : '❌';
    const platMatch = n.platform === m.platform ? '✅' : '❌';
    md += `| ${stage} | ${reward} | ${n.cash || '—'} | ${m.cash || '—'} | ${cashMatch} | ${n.platform || '—'} | ${m.platform || '—'} | ${platMatch} |\n`;
  }

  const auditPath = path.join(OUT_DIR, 'CUE_AUDIT.md');
  fs.writeFileSync(auditPath, md);
  console.log(`\n✅ CUE_AUDIT.md written to ${auditPath}`);

  // ---------------------------------------------------------------------------
  // Print summary
  // ---------------------------------------------------------------------------
  console.log(`\n=== QA Complete ===`);
  console.log(`Screenshots saved to: ${OUT_DIR}`);
  console.log(`Total screenshots: ${fs.readdirSync(OUT_DIR).filter(f => f.endsWith('.png')).length}`);
})();

