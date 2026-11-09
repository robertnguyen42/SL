/**
 * Bản tin Di trú — web app nội bộ SI (chỉ tài khoản @si.im truy cập, xem appsscript.json: access DOMAIN).
 *
 * Dữ liệu: GitHub Actions (repo robertnguyen42/SL) lấy tin 30 phút/lần, dịch bằng Claude, lọc chương trình SI,
 * xuất docs/data/news_si.json. Web app đọc file đó qua UrlFetchApp, lưu đệm 5 phút.
 * Danh sách Facebook đối thủ đọc từ Google Sheet nội bộ (Script Property LIB_FB_SHEET_ID), không để trên GitHub.
 *
 * Quy ước để gộp vào app Case Management sau này: mọi hàm có tiền tố Lib_ / lib_, doGet chỉ gọi Lib_render().
 */

var LIB_DATA_URL = 'https://raw.githubusercontent.com/robertnguyen42/SL/main/docs/data/news_si.json';
var LIB_CACHE_SEC = 300;          // lưu đệm 5 phút
var LIB_CHUNK = 30000;            // CacheService giới hạn 100 KB mỗi khoá (ký tự tiếng Việt tới 3 byte)

function doGet(e) {
  return Lib_render(e);
}

function Lib_render(e) {
  var t = HtmlService.createTemplateFromFile('LibraryPage');
  // Chặn chèn mã qua tham số URL: thoát ký tự < trước khi nhúng vào <script>
  t.params = JSON.stringify((e && e.parameter) || {}).replace(/</g, '\\u003c');
  return t.evaluate()
    .setTitle('Bản tin Di trú')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.DEFAULT);
}

/** Trả về chuỗi JSON dữ liệu tin (client tự JSON.parse cho nhanh). */
function Lib_getData() {
  var cached = lib_cacheGet_('lib_news');
  if (cached) return cached;
  var res = UrlFetchApp.fetch(LIB_DATA_URL, { muteHttpExceptions: true, headers: { 'Cache-Control': 'no-cache' } });
  if (res.getResponseCode() !== 200) {
    throw new Error('Không tải được dữ liệu tin (HTTP ' + res.getResponseCode() + ')');
  }
  var text = res.getContentText('UTF-8');
  lib_cachePut_('lib_news', text);
  return text;
}

/** Danh sách trang Facebook đối thủ từ Google Sheet nội bộ: cột A tên, B link, C ghi chú (dòng 1 là tiêu đề). */
function Lib_getFacebook() {
  var id = PropertiesService.getScriptProperties().getProperty('LIB_FB_SHEET_ID');
  if (!id) return [];
  var rows = SpreadsheetApp.openById(id).getSheets()[0].getDataRange().getValues().slice(1);
  return rows.filter(function (r) { return r[0] && r[1]; })
             .map(function (r) { return { name: String(r[0]), url: String(r[1]), note: String(r[2] || '') }; });
}

/**
 * Chạy MỘT LẦN trong editor: tạo Google Sheet "SL | FACEBOOK ĐỐI THỦ ĐỊNH CƯ" từ danh sách hiện có trên GitHub
 * và lưu ID vào Script Properties. Sau đó danh sách chỉ sửa trong Sheet này.
 */
function Lib_setupFacebookSheet() {
  var props = PropertiesService.getScriptProperties();
  if (props.getProperty('LIB_FB_SHEET_ID')) {
    Logger.log('Đã có Sheet: https://docs.google.com/spreadsheets/d/' + props.getProperty('LIB_FB_SHEET_ID'));
    return;
  }
  var src = 'https://raw.githubusercontent.com/robertnguyen42/SL/main/docs/data/facebook.json';
  var pages = [];
  try { pages = JSON.parse(UrlFetchApp.fetch(src).getContentText('UTF-8')).pages || []; } catch (err) { pages = []; }
  var ss = SpreadsheetApp.create('SL | FACEBOOK ĐỐI THỦ ĐỊNH CƯ');
  var sh = ss.getSheets()[0];
  var values = [['TÊN', 'LINK FACEBOOK', 'GHI CHÚ']].concat(pages.map(function (p) { return [p.name, p.url, p.note || '']; }));
  sh.getRange(1, 1, values.length, 3).setValues(values);
  sh.setFrozenRows(1);
  props.setProperty('LIB_FB_SHEET_ID', ss.getId());
  Logger.log('Đã tạo Sheet với ' + pages.length + ' trang: ' + ss.getUrl());
}

function lib_cacheGet_(key) {
  var c = CacheService.getScriptCache();
  var n = c.get(key + '_n');
  if (!n) return null;
  var keys = [];
  for (var i = 0; i < +n; i++) keys.push(key + '_' + i);
  var parts = c.getAll(keys);
  var out = '';
  for (var j = 0; j < keys.length; j++) {
    if (parts[keys[j]] == null) return null;
    out += parts[keys[j]];
  }
  return out;
}

function lib_cachePut_(key, text) {
  var c = CacheService.getScriptCache(), obj = {}, n = 0;
  for (var i = 0; i < text.length; i += LIB_CHUNK) obj[key + '_' + (n++)] = text.slice(i, i + LIB_CHUNK);
  obj[key + '_n'] = String(n);
  try { c.putAll(obj, LIB_CACHE_SEC); } catch (err) { /* quá giới hạn cache thì bỏ qua, lần sau tải lại */ }
}

/* ===================== Tin chọn cho bản tin tuần (cắm cờ) =====================
 * Lưu ở Google Sheet nội bộ "SL | BẢN TIN TUẦN – TIN ĐÃ CHỌN" (Script Property LIB_FLAG_SHEET_ID; tự tạo lần đầu).
 * Cả team dùng chung một danh sách. Mỗi tin thuộc "tuần bản tin" = tuần (thứ Hai–Chủ nhật) lúc được cắm cờ.
 */
var LIB_FLAG_COLS = ['id', 'tuan', 'quoc_gia', 'tieu_de', 'tieu_de_goc', 'tom_tat', 'link', 'nguon', 'ngay_dang',
                     'chuong_trinh', 'nguoi_chon', 'thoi_diem', 'ghi_chu'];

function lib_flagSheet_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('LIB_FLAG_SHEET_ID');
  if (id) return SpreadsheetApp.openById(id).getSheets()[0];
  var ss = SpreadsheetApp.create('SL | BẢN TIN TUẦN – TIN ĐÃ CHỌN');
  var sh = ss.getSheets()[0];
  sh.getRange(1, 1, 1, LIB_FLAG_COLS.length).setValues([LIB_FLAG_COLS]).setFontWeight('bold');
  sh.setFrozenRows(1);
  props.setProperty('LIB_FLAG_SHEET_ID', ss.getId());
  return sh;
}

function lib_weekStart_(d) {
  var x = new Date(d.getTime());
  var tz = 'Asia/Ho_Chi_Minh';
  var dow = +Utilities.formatDate(x, tz, 'u');        // 1 = thứ Hai … 7 = Chủ nhật
  x.setDate(x.getDate() - (dow - 1));
  return Utilities.formatDate(x, tz, 'yyyy-MM-dd');
}

function lib_rows_(sh) {
  var v = sh.getDataRange().getValues();
  var head = v.shift();
  return v.map(function (r, n) {
    var o = { _row: n + 2 };
    head.forEach(function (h, i) { o[h] = r[i] instanceof Date ? Utilities.formatDate(r[i], 'Asia/Ho_Chi_Minh', 'yyyy-MM-dd') : r[i]; });
    return o;
  }).filter(function (o) { return o.id; });
}

/** Toàn bộ tin đã cắm cờ (mới nhất trước) và email người đang xem. */
function Lib_getFlags() {
  var rows = lib_rows_(lib_flagSheet_());
  rows.forEach(function (r) { delete r._row; });
  return { me: Session.getActiveUser().getEmail(), flags: rows.reverse() };
}

/** Cắm cờ / bỏ cờ một tin. item: {id, country, title, title_orig, summary, link, publisher, published, programs}. */
function Lib_toggleFlag(item) {
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sh = lib_flagSheet_();
    var hit = lib_rows_(sh).filter(function (r) { return r.id === item.id; })[0];
    if (hit) { sh.deleteRow(hit._row); return { flagged: false }; }
    var now = new Date();
    sh.appendRow([item.id, lib_weekStart_(now), item.country, item.title, item.title_orig || '', item.summary || '',
                  item.link, item.publisher || '', String(item.published || '').slice(0, 10), (item.programs || []).join(', '),
                  Session.getActiveUser().getEmail(), now, '']);
    return { flagged: true };
  } finally {
    lock.releaseLock();
  }
}

/** Sửa tiêu đề / tóm tắt / ghi chú của tin đã chọn (dùng khi soạn email bản tin). */
function Lib_updateFlag(id, fields) {
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sh = lib_flagSheet_();
    var hit = lib_rows_(sh).filter(function (r) { return r.id === id; })[0];
    if (!hit) return false;
    ['tieu_de', 'tom_tat', 'ghi_chu', 'tuan'].forEach(function (k) {
      if (fields[k] != null) sh.getRange(hit._row, LIB_FLAG_COLS.indexOf(k) + 1).setValue(String(fields[k]));
    });
    return true;
  } finally {
    lock.releaseLock();
  }
}
