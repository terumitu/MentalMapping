/**
 * sheet_writer.gs — mood_log_{user} シートへの not_recorded 行 append。
 *
 * 17 列構成 (§4.3.2 / arch_mentalmap_v1_2.md §A.1):
 *   A:date  B:mood  C:energy  D:thinking  E:focus  F:sleep_hours
 *   G:weather  H:medication  I:period  J:recorded_at  K:time_of_day
 *   L:daily_aspects  M:record_id  N:record_status  O:superseded_by
 *   P:entry_mode  Q:input_user
 *
 * not_recorded 行の値仕様 (§4.3.2):
 *   B〜E (mood/energy/thinking/focus): 空
 *   F〜I (sleep_hours/weather/medication/period): 空
 *   J: バッチ実行時刻 (JST ISO)
 *   K: 'morning' or 'evening'
 *   L: 空 (Phase 2 で埋める)
 *   M: record_id (makeRecordId で生成)
 *   N: 'active'
 *   O: 空
 *   P: 'not_recorded'
 *   Q: input_user
 */

const MOOD_LOG_COLUMNS = 17;

/**
 * not_recorded 行を 1 件 append する。
 * 呼び出し側で冪等性は既に確認済 (generateNotRecorded 側で二段確認)。
 */
function appendNotRecordedRow(user, dateStr, tod, recordedAtIso, unixTs) {
  const sheetName = user.sheetName;
  if (!sheetName) throw new Error('user.sheetName is empty');
  const sheet = _openSheet(sheetName);
  const recordId = makeRecordId(user.inputUser, dateStr, tod, unixTs);
  const row = _buildNotRecordedRow({
    inputUser: user.inputUser,
    dateStr: dateStr,
    tod: tod,
    recordedAtIso: recordedAtIso,
    recordId: recordId,
  });
  sheet.appendRow(row);
  return recordId;
}

/** not_recorded 行配列を構築 (17 列)。 */
function _buildNotRecordedRow(spec) {
  const row = new Array(MOOD_LOG_COLUMNS).fill('');
  row[0] = spec.dateStr;            // A: date
  // B〜I は空のまま
  row[9] = spec.recordedAtIso;      // J: recorded_at
  row[10] = spec.tod;                // K: time_of_day
  // L: daily_aspects は空
  row[12] = spec.recordId;           // M: record_id
  row[13] = 'active';                // N: record_status
  // O: superseded_by は空
  row[15] = 'not_recorded';          // P: entry_mode
  row[16] = spec.inputUser;          // Q: input_user
  return row;
}

/**
 * mood_log_{user} シートから既存 (date, time_of_day) 全スロットを Set 化。
 * record_status 不問 (active / superseded 両方含む) → §4.3.2 冪等性条件。
 * 返値: Set<"YYYY-MM-DD|morning|evening"> の文字列集合。
 */
function loadExistingSlots(sheetName) {
  const sheet = _openSheet(sheetName);
  const values = sheet.getDataRange().getValues();
  const slots = new Set();
  if (values.length < 2) return slots;
  const header = values[0].map(function(h) { return String(h).trim(); });
  const idxDate = header.indexOf('date');
  const idxTod = header.indexOf('time_of_day');
  if (idxDate < 0 || idxTod < 0) {
    throw new Error('Header missing date/time_of_day in ' + sheetName);
  }
  for (let i = 1; i < values.length; i++) {
    const row = values[i];
    const d = _cellDateStr(row[idxDate]);
    const t = _cellStr(row[idxTod]);
    if (!d || !t) continue;
    slots.add(_slotKey(d, t));
  }
  return slots;
}

/** append 直前の二段目確認: 指定シートで単一スロットが既存か。 */
function slotExists(sheetName, dateStr, tod) {
  const slots = loadExistingSlots(sheetName);
  return slots.has(_slotKey(dateStr, tod));
}

function _slotKey(dateStr, tod) {
  return dateStr + '|' + tod;
}
