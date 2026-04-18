/**
 * config_reader.gs — config_users / config_exclude シートを単一真実源として読む。
 *
 * config_users 列構成:
 *   A: input_user
 *   B: display_name
 *   C: sheet_name
 *   D: morning_start
 *   E: morning_end
 *   F: evening_start
 *   G: evening_end
 *   H: start_date       ← α-D が遡及開始する日 (GAS バッチの起点)
 *
 * ※ Python 側 devtools/migrate_v1_2_steps_populate.NOT_RECORDED_START_DATES
 *    (masuda/nishide=2026-04-11) は α-C マイグレーションの起点日であり、
 *    本 start_date (α-D の起点) とは別概念。α-C が 2026-04-18 までを遡及済
 *    なので α-D の start_date は 2026-04-19 以降となる。
 *
 * config_exclude 列構成:
 *   A: input_user  B: date  C: time_of_day  D: reason
 *
 * ※ Python 側 NOT_RECORDED_EXCLUDE と内容一致必須。
 *    変更時は両方同時更新 + mm_notes 起票 (将来 CLAUDE.md §10 予定)。
 */

const CONFIG_USERS_SHEET = 'config_users';
const CONFIG_EXCLUDE_SHEET = 'config_exclude';

/** config_users シートを読み込み User[] を返す。 */
function readConfigUsers() {
  const sheet = _openSheet(CONFIG_USERS_SHEET);
  const values = sheet.getDataRange().getValues();
  if (values.length < 1) {
    throw new Error('config_users is empty (header row required)');
  }
  const users = [];
  for (let i = 1; i < values.length; i++) {
    const row = values[i];
    const inputUser = _cellStr(row[0]);
    if (!inputUser) continue;
    users.push(_buildUser(row));
  }
  return users;
}

/** 1 行分を User struct に変換。window 未定義は isPending=true。 */
function _buildUser(row) {
  const inputUser = _cellStr(row[0]);
  const displayName = _cellStr(row[1]);
  const sheetName = _cellStr(row[2]);
  const morningStart = _cellStr(row[3]);
  const morningEnd = _cellStr(row[4]);
  const eveningStart = _cellStr(row[5]);
  const eveningEnd = _cellStr(row[6]);
  const startDateStr = _cellStr(row[7]);

  const morningWindow = parseWindow(morningStart, morningEnd);
  const eveningWindow = parseWindow(eveningStart, eveningEnd);
  const isPending = (morningWindow === null || eveningWindow === null);

  return {
    inputUser: inputUser,
    displayName: displayName,
    sheetName: sheetName,
    morningWindow: morningWindow,
    eveningWindow: eveningWindow,
    startDate: startDateStr ? parseDateJst(startDateStr) : null,
    startDateStr: startDateStr,
    isPending: isPending,
  };
}

/**
 * config_exclude シートを読み込み Set<"user|date|tod"> を返す。
 * シート不在でも空 Set を返す (EXCLUDE ゼロ運用も許容)。
 */
function readConfigExclude() {
  const ss = _openSpreadsheet();
  const sheet = ss.getSheetByName(CONFIG_EXCLUDE_SHEET);
  if (!sheet) {
    Logger.log('config_exclude sheet not found, treating as empty set');
    return new Set();
  }
  const values = sheet.getDataRange().getValues();
  const excludeSet = new Set();
  for (let i = 1; i < values.length; i++) {
    const row = values[i];
    const inputUser = _cellStr(row[0]);
    const dateStr = _cellDateStr(row[1]);
    const tod = _cellStr(row[2]);
    if (!inputUser || !dateStr || !tod) continue;
    excludeSet.add(_excludeKey(inputUser, dateStr, tod));
  }
  return excludeSet;
}

/** EXCLUDE 判定用のキー生成。 */
function _excludeKey(inputUser, dateStr, tod) {
  return inputUser + '|' + dateStr + '|' + tod;
}

/** セル値を trim 済み文字列化。Date インスタンスはそのまま toString (日付は _cellDateStr を使うこと)。 */
function _cellStr(v) {
  if (v === null || v === undefined) return '';
  return String(v).trim();
}

/**
 * date セルを 'YYYY-MM-DD' 文字列化。Sheets が Date として解釈した場合は
 * jstDateString で整形、文字列のままなら trim のみ。
 */
function _cellDateStr(v) {
  if (v === null || v === undefined) return '';
  if (v instanceof Date) return jstDateString(v);
  return String(v).trim();
}
