/**
 * util.gs — 共通ユーティリティ。
 *
 * - JST 時刻フォーマット / ISO lenient 化 / record_id 生成 / Date 演算 /
 *   window 構造体パース / SPREADSHEET_ID オープンのヘルパ群。
 *
 * standalone GAS プロジェクトのため SpreadsheetApp.getActiveSpreadsheet()
 * は使用しない。_openSpreadsheet() / _openSheet() を経由する。
 */

const TZ_JST = 'Asia/Tokyo';

/**
 * Script Properties から SPREADSHEET_ID を取得して Spreadsheet を開く。
 * 未設定時は明示エラーで呼び出し側の try-catch に委ねる。
 */
function _openSpreadsheet() {
  const id = PropertiesService.getScriptProperties()
    .getProperty('SPREADSHEET_ID');
  if (!id) {
    throw new Error('SPREADSHEET_ID is not configured in Script Properties');
  }
  return SpreadsheetApp.openById(id);
}

/**
 * 指定名のシートを _openSpreadsheet() 経由で取得する。
 * 不在時は明示エラー。
 */
function _openSheet(sheetName) {
  const ss = _openSpreadsheet();
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    throw new Error('Sheet not found: ' + sheetName);
  }
  return sheet;
}

/** 現在の JST Date を返す (Apps Script の new Date は UTC 相当だが formatDate で JST 変換)。 */
function jstNow() {
  return new Date();
}

/** JST の ISO 文字列 'YYYY-MM-DDTHH:mm:ss' を返す (Z 付けない)。 */
function jstIsoString(d) {
  return Utilities.formatDate(d, TZ_JST, "yyyy-MM-dd'T'HH:mm:ss");
}

/** JST の日付文字列 'YYYY-MM-DD' を返す。 */
function jstDateString(d) {
  return Utilities.formatDate(d, TZ_JST, 'yyyy-MM-dd');
}

/**
 * 単桁時刻を含む ISO 8601 風文字列をゼロパディング。
 * 'T9:34:37' -> 'T09:34:37'。
 * Python 側 migrate_v1_2._normalize_iso_jst と同方針。
 */
function normalizeIsoJst(s) {
  if (!s) return s;
  const str = String(s);
  return str.replace(/T(\d):(\d\d):(\d\d)/, function(_, h, m, sec) {
    return 'T0' + h + ':' + m + ':' + sec;
  });
}

/**
 * record_id を '{input_user}_{date}_{time_of_day}_{unix_ts}' 形式で生成。
 * Python 側 record_chain.generate_record_id と同形式。
 */
function makeRecordId(inputUser, dateStr, tod, unixTs) {
  if (!inputUser) throw new Error('inputUser must not be empty');
  if (!dateStr) throw new Error('dateStr must not be empty');
  if (tod !== 'morning' && tod !== 'evening') {
    throw new Error("tod must be 'morning' or 'evening', got: " + tod);
  }
  if (typeof unixTs !== 'number' || !isFinite(unixTs)) {
    throw new Error('unixTs must be a finite number, got: ' + unixTs);
  }
  return inputUser + '_' + dateStr + '_' + tod + '_' + Math.floor(unixTs);
}

/** Date -> UNIX 秒 (int)。 */
function unixTsOf(d) {
  return Math.floor(d.getTime() / 1000);
}

/**
 * 'YYYY-MM-DD' 文字列 -> Date (JST 00:00:00 相当)。
 * Date オブジェクトは UTC ベースだが、日付跨ぎ比較は jstDateString を使うため実害なし。
 */
function parseDateJst(dateStr) {
  if (!dateStr) throw new Error('dateStr must not be empty');
  const m = String(dateStr).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) throw new Error('Invalid date format: ' + dateStr);
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

/** Date に day 日加算した新 Date を返す (非破壊)。 */
function addDays(d, days) {
  const nd = new Date(d.getTime());
  nd.setDate(nd.getDate() + days);
  return nd;
}

/**
 * 'HH:MM' 文字列 2 つを window 構造体に変換。
 * 空文字は null を返す (pending ユーザー判定用)。
 * 'HH:MM' -> { h: Number, m: Number }
 */
function parseWindow(startStr, endStr) {
  if (!startStr || !endStr) return null;
  return {
    start: _parseHhmm(startStr),
    end: _parseHhmm(endStr),
  };
}

function _parseHhmm(s) {
  const m = String(s).match(/^(\d{1,2}):(\d{2})$/);
  if (!m) throw new Error('Invalid HH:MM format: ' + s);
  return { h: Number(m[1]), m: Number(m[2]) };
}

/**
 * Date 配列を [startDate, endDate] (両端含む) で列挙する。
 * 返値は 'YYYY-MM-DD' 文字列配列。
 */
function enumerateDates(startDate, endDate) {
  const result = [];
  let d = new Date(startDate.getTime());
  while (d.getTime() <= endDate.getTime()) {
    result.push(jstDateString(d));
    d = addDays(d, 1);
  }
  return result;
}
