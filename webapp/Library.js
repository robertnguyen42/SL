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
