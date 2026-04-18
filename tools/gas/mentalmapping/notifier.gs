/**
 * notifier.gs — Discord Webhook 通知 + gas_batch_log シート追記。
 *
 * Discord:
 *   - Script Properties DISCORD_WEBHOOK_URL を参照
 *   - 未設定時は warn + skip (呼び出し側を妨げない)
 *   - 送信失敗時も catch して Logger.log のみ
 *
 * gas_batch_log 列構成:
 *   A: execution_at
 *   B: mode               (initial_backfill_dry / initial_backfill_exec / daily / test)
 *   C: target_date_range  ('YYYY-MM-DD..YYYY-MM-DD' or 'YYYY-MM-DD' 単日)
 *   D: users_scanned      (カンマ区切りユーザー名)
 *   E: gaps_generated     (数値 or 'dry' 時は検出件数)
 *   F: errors             (カンマ区切りエラー要約 / 無ければ空)
 *   G: elapsed_ms         (数値)
 */

const BATCH_LOG_SHEET = 'gas_batch_log';

/** Discord Webhook に content を 1 件 POST。失敗は catch のみ。 */
function notifyDiscord(content) {
  const url = PropertiesService.getScriptProperties()
    .getProperty('DISCORD_WEBHOOK_URL');
  if (!url) {
    Logger.log('DISCORD_WEBHOOK_URL is not configured, skip notification');
    return;
  }
  try {
    const payload = JSON.stringify({ content: content });
    UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: payload,
      muteHttpExceptions: true,
    });
  } catch (err) {
    Logger.log('Discord notify failed: ' + err.message);
  }
}

/**
 * gas_batch_log シートに 1 行追記。
 * シート不在時は明示エラー (前提作業で作成必須)。
 */
function appendBatchLog(entry) {
  const sheet = _openSheet(BATCH_LOG_SHEET);
  const row = [
    entry.executionAt || jstIsoString(jstNow()),
    entry.mode || '',
    entry.targetDateRange || '',
    entry.usersScanned || '',
    entry.gapsGenerated !== undefined ? entry.gapsGenerated : '',
    entry.errors || '',
    entry.elapsedMs !== undefined ? entry.elapsedMs : '',
  ];
  sheet.appendRow(row);
}

/**
 * Discord 通知用サマリ文字列を構築。
 * results: { byUser: { user: {status, detected, generated} }, total, errors }
 */
function summarizeResult(mode, results) {
  const lines = ['[' + mode + ']'];
  const users = Object.keys(results.byUser || {});
  users.forEach(function(u) {
    const r = results.byUser[u];
    if (r.status === 'pending') {
      lines.push('  ' + u + ': skipped (pending)');
    } else {
      const detected = r.detected !== undefined ? r.detected : 0;
      const generated = r.generated !== undefined ? r.generated : 0;
      lines.push('  ' + u + ': detected=' + detected + ' generated=' + generated);
    }
  });
  lines.push('total generated: ' + (results.total || 0));
  if (results.errors && results.errors.length > 0) {
    lines.push('errors: ' + results.errors.join(', '));
  }
  return lines.join('\n');
}
