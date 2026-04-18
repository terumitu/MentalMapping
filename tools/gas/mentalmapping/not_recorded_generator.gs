/**
 * not_recorded_generator.gs — gap 検出 + 冪等性確認 + 生成オーケストレーション。
 *
 * gap 定義 (§4.3.2 / §A.5.6 / §A.7.5):
 *   対象範囲 [startDate, endDate] の (date, tod='morning'/'evening') 組のうち、
 *   以下を全て満たすものを生成対象とする:
 *     1. mood_log_{user} に同一 (date, tod) レコードが **任意の record_status** で不在
 *     2. config_exclude シートに (user, date, tod) が登録されていない
 *
 * 冪等性二段構え:
 *   (1) バッチ開始時に全体スキャン (loadExistingSlots)
 *   (2) append 直前にもう一度 slotExists で再確認 (並行書き込み対策)
 */

const TOD_VALUES = ['morning', 'evening'];

/**
 * 単一ユーザーの gap を列挙する。
 * pending ユーザーは呼び出し側で除外される前提 (本関数は pending でも実行可能だが
 * 空配列を返す)。
 *
 * 返値: [{ user, dateStr, tod }, ...]
 */
function scanGaps(user, startDate, endDate, excludeSet) {
  if (user.isPending) return [];
  if (!startDate || !endDate) {
    throw new Error('scanGaps requires startDate and endDate');
  }
  if (startDate.getTime() > endDate.getTime()) return [];

  const existing = loadExistingSlots(user.sheetName);
  const dates = enumerateDates(startDate, endDate);
  const gaps = [];
  for (let i = 0; i < dates.length; i++) {
    const dateStr = dates[i];
    for (let j = 0; j < TOD_VALUES.length; j++) {
      const tod = TOD_VALUES[j];
      const slot = dateStr + '|' + tod;
      if (existing.has(slot)) continue;
      if (excludeSet.has(_excludeKey(user.inputUser, dateStr, tod))) continue;
      gaps.push({
        user: user,
        dateStr: dateStr,
        tod: tod,
      });
    }
  }
  return gaps;
}

/**
 * gaps を順次 append する。冪等性の二段目確認を append 直前に実施。
 *
 * execute=false: ログのみ / 戻り値の generated は 0
 * execute=true:  実 append
 *
 * 返値: { detected, generated, errors: [] }
 */
function generateNotRecorded(gaps, execute) {
  const result = { detected: gaps.length, generated: 0, errors: [] };
  if (gaps.length === 0) return result;

  const recordedAtIso = jstIsoString(jstNow());
  const unixTs = unixTsOf(jstNow());

  for (let i = 0; i < gaps.length; i++) {
    const g = gaps[i];
    try {
      if (!execute) {
        Logger.log('[dry] would append: ' + g.user.inputUser + ' ' + g.dateStr + ' ' + g.tod);
        continue;
      }
      // 二段目確認: append 直前にもう一度存在チェック
      if (slotExists(g.user.sheetName, g.dateStr, g.tod)) {
        Logger.log('[skip] concurrent write detected: ' +
          g.user.inputUser + ' ' + g.dateStr + ' ' + g.tod);
        continue;
      }
      appendNotRecordedRow(g.user, g.dateStr, g.tod, recordedAtIso, unixTs);
      result.generated += 1;
    } catch (err) {
      const msg = g.user.inputUser + '/' + g.dateStr + '/' + g.tod + ':' + err.message;
      result.errors.push(msg);
      Logger.log('[error] ' + msg);
    }
  }
  return result;
}

/**
 * 複数ユーザー横断でまとめて gap 検出 + 生成を行う。
 *
 * 返値: {
 *   byUser: { userId: { status: 'pending'|'ok', detected, generated, errors } },
 *   total, errors
 * }
 */
function runGenerationAcrossUsers(users, startDateResolver, endDate, execute) {
  const excludeSet = readConfigExclude();
  const summary = { byUser: {}, total: 0, errors: [] };

  for (let i = 0; i < users.length; i++) {
    const user = users[i];
    if (user.isPending) {
      summary.byUser[user.inputUser] = { status: 'pending', detected: 0, generated: 0 };
      continue;
    }
    const startDate = startDateResolver(user);
    if (!startDate) {
      summary.byUser[user.inputUser] = {
        status: 'skipped',
        detected: 0,
        generated: 0,
        errors: ['no start_date'],
      };
      continue;
    }
    const gaps = scanGaps(user, startDate, endDate, excludeSet);
    const r = generateNotRecorded(gaps, execute);
    summary.byUser[user.inputUser] = {
      status: 'ok',
      detected: r.detected,
      generated: r.generated,
      errors: r.errors,
    };
    summary.total += r.generated;
    if (r.errors.length > 0) {
      r.errors.forEach(function(e) { summary.errors.push(e); });
    }
  }
  return summary;
}
