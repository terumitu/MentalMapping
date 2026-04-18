/**
 * main.gs — エントリーポイント。
 *
 * 本番トリガー:
 *   runInitialBackfillDry  (手動・dry-run)
 *   runInitialBackfill     (手動・実行)
 *   runDailyBatch          (time-driven・毎日 03:00 JST)
 *
 * テスト用手動トリガー (Lock なし・read-only or dummy):
 *   testConfigRead / testScanGapsMasuda / testScanGapsNishide /
 *   testScanGapsSuyasu / testNotifyDiscord / testAppendBatchLog
 */

const MODE_INIT_DRY = 'initial_backfill_dry';
const MODE_INIT_EXEC = 'initial_backfill_exec';
const MODE_DAILY = 'daily';

/**
 * LockService でスクリプト Lock を取得して fn を実行。
 * 30 秒 timeout で GAS 多重起動を防止する。
 */
function _withLock(fn) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) {
    throw new Error('Lock acquisition failed (another instance running)');
  }
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

// ==========================================================================
// 本番エントリーポイント
// ==========================================================================

/** 初回遡及の dry-run (実 append なし / Discord 通知あり)。 */
function runInitialBackfillDry() {
  _withLock(function() { return _runInitialBackfill(false); });
}

/** 初回遡及の実行 (実 append + 冪等性二段確認)。 */
function runInitialBackfill() {
  _withLock(function() { return _runInitialBackfill(true); });
}

/** 毎日 03:00 JST の time-driven trigger で実行。 */
function runDailyBatch() {
  _withLock(_runDailyBatch);
}

// ==========================================================================
// 実装本体
// ==========================================================================

function _runInitialBackfill(execute) {
  const mode = execute ? MODE_INIT_EXEC : MODE_INIT_DRY;
  const started = new Date();
  let summary = null;
  let errorMsg = null;
  try {
    const users = readConfigUsers();
    const endDate = addDays(jstNow(), -1);  // today - 1 (JST)
    summary = runGenerationAcrossUsers(
      users,
      function(u) { return u.startDate; },
      endDate,
      execute
    );
    _logAndNotify(mode, summary, users, null, endDate, started, errorMsg);
  } catch (err) {
    errorMsg = err.message;
    Logger.log('[' + mode + '] fatal: ' + err.message);
    notifyDiscord('[' + mode + '] fatal error: ' + err.message);
    _safeAppendBatchLog({
      mode: mode,
      targetDateRange: '',
      usersScanned: '',
      gapsGenerated: '',
      errors: errorMsg,
      elapsedMs: new Date().getTime() - started.getTime(),
    });
    throw err;
  }
}

function _runDailyBatch() {
  const started = new Date();
  const targetDate = addDays(jstNow(), -1);
  let errorMsg = null;
  try {
    const users = readConfigUsers();
    const summary = runGenerationAcrossUsers(
      users,
      function(_u) { return targetDate; },
      targetDate,
      true
    );
    const hasErrors = summary.errors.length > 0;
    _safeAppendBatchLog({
      mode: MODE_DAILY,
      targetDateRange: jstDateString(targetDate),
      usersScanned: _listUserIds(users),
      gapsGenerated: summary.total,
      errors: hasErrors ? summary.errors.join(', ') : '',
      elapsedMs: new Date().getTime() - started.getTime(),
    });
    if (hasErrors) {
      notifyDiscord(summarizeResult(MODE_DAILY, summary));
    }
    // 正常時は Discord 通知しない (§A.7 運用方針)
  } catch (err) {
    errorMsg = err.message;
    Logger.log('[' + MODE_DAILY + '] fatal: ' + err.message);
    notifyDiscord('[' + MODE_DAILY + '] fatal error: ' + err.message);
    _safeAppendBatchLog({
      mode: MODE_DAILY,
      targetDateRange: jstDateString(targetDate),
      usersScanned: '',
      gapsGenerated: '',
      errors: errorMsg,
      elapsedMs: new Date().getTime() - started.getTime(),
    });
    throw err;
  }
}

function _logAndNotify(mode, summary, users, _target, endDate, started, errorMsg) {
  _safeAppendBatchLog({
    mode: mode,
    targetDateRange: _formatRange(users, endDate),
    usersScanned: _listUserIds(users),
    gapsGenerated: summary.total,
    errors: summary.errors.length > 0 ? summary.errors.join(', ') : (errorMsg || ''),
    elapsedMs: new Date().getTime() - started.getTime(),
  });
  notifyDiscord(summarizeResult(mode, summary));
}

function _safeAppendBatchLog(entry) {
  try {
    appendBatchLog(entry);
  } catch (err) {
    Logger.log('appendBatchLog failed: ' + err.message);
  }
}

function _formatRange(users, endDate) {
  const starts = users
    .filter(function(u) { return !u.isPending && u.startDate; })
    .map(function(u) { return u.startDate.getTime(); });
  if (starts.length === 0) return jstDateString(endDate);
  const minStart = new Date(Math.min.apply(null, starts));
  return jstDateString(minStart) + '..' + jstDateString(endDate);
}

function _listUserIds(users) {
  return users.map(function(u) { return u.inputUser; }).join(',');
}

// ==========================================================================
// テスト用手動トリガー
// ==========================================================================

/** config_users / config_exclude を Logger.log に整形出力。 */
function testConfigRead() {
  const users = readConfigUsers();
  Logger.log('--- config_users (' + users.length + ' rows) ---');
  users.forEach(function(u) {
    Logger.log(
      u.inputUser + ' sheet=' + u.sheetName +
      ' pending=' + u.isPending +
      ' start=' + u.startDateStr
    );
  });
  const ex = readConfigExclude();
  Logger.log('--- config_exclude (' + ex.size + ' entries) ---');
  ex.forEach(function(k) { Logger.log(k); });
}

function testScanGapsMasuda() { _testScanGaps('masuda'); }
function testScanGapsNishide() { _testScanGaps('nishide'); }
function testScanGapsSuyasu() { _testScanGaps('suyasu'); }

function _testScanGaps(inputUser) {
  const users = readConfigUsers();
  const user = users.filter(function(u) { return u.inputUser === inputUser; })[0];
  if (!user) { Logger.log('user not found: ' + inputUser); return; }
  if (user.isPending) {
    Logger.log(inputUser + ': pending (skipped)');
    return;
  }
  const endDate = addDays(jstNow(), -1);
  const excludeSet = readConfigExclude();
  const gaps = scanGaps(user, user.startDate, endDate, excludeSet);
  Logger.log(inputUser + ' gaps=' + gaps.length +
    ' range=' + user.startDateStr + '..' + jstDateString(endDate));
  gaps.forEach(function(g) { Logger.log('  ' + g.dateStr + ' ' + g.tod); });
}

/** Discord Webhook 疎通確認。 */
function testNotifyDiscord() {
  notifyDiscord('[test] α-D notifier疎通確認 ' + jstIsoString(jstNow()));
  Logger.log('Discord test notification sent');
}

/** gas_batch_log 書き込み疎通確認。 */
function testAppendBatchLog() {
  appendBatchLog({
    mode: 'test',
    targetDateRange: jstDateString(jstNow()),
    usersScanned: 'test',
    gapsGenerated: 0,
    errors: '',
    elapsedMs: 0,
  });
  Logger.log('gas_batch_log test row appended');
}
