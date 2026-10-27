# Video Maker — dựng video TikTok / Shorts / Reels hàng loạt

Ứng dụng chạy trên máy Windows, có giao diện web (mở trong trình duyệt tại `http://127.0.0.1:8765`).
Nó ghép ảnh bình luận, giọng đọc, hiệu ứng, video nền và nhạc nền thành video dọc 1080×1920, 30 FPS, định dạng MP4.

## Chạy

Nhấp đúp **`run.bat`**. Lần đầu chạy, file này sẽ tạo `.venv` và cài các thư viện trong `requirements.txt`.
Cần có Python 3.10 trở lên. Bạn không phải cài FFmpeg riêng vì gói `imageio-ffmpeg` đã kèm sẵn.

## Thư mục

```
VideoMaker/
├── Backgrounds/      video nền (.mp4 .mov .mkv .webm…) — mỗi lần dựng chọn ngẫu nhiên
├── Contents/         mỗi thư mục con = 1 video; ảnh bên trong sắp theo tên (01.png, 02.png…)
├── SoundEffects/     hiệu ứng âm thanh — phát ngẫu nhiên sau khi đọc xong mỗi bình luận
├── SoundBackground/  nhạc nền — luôn được giữ nhỏ hơn giọng đọc và tự giảm thêm khi đang đọc
├── Stickers/         sticker (.png/.webp/.gif) gắn ở góc từng bình luận
├── GIFs/             GIF/WebP động gắn trên/dưới/góc từng bình luận
├── VideoEffects/     clip meme (có tiếng) phát sau khi đọc xong một bình luận
└── Output/           video thành phẩm
```

Có thể đổi các đường dẫn này trong tab **Cài đặt**.
Lời đọc chỉ cần là nội dung bình luận. Nếu đặt sẵn file `01.txt` cạnh `01.png`, hoặc một file `script.txt` (mỗi đoạn cách nhau bằng một dòng trống), ứng dụng sẽ dùng nội dung đó làm lời đọc ban đầu.

## Quy trình

1. Tab **Content**: danh sách tự cập nhật khi bạn thêm thư mục. Bấm **Biên tập** để mở một content.
2. Tab **Biên tập & Preview** có các phần sau:
   - Nhập lời đọc cho từng ảnh. Tick “Không đọc” nếu muốn bỏ qua ảnh đó.
   - **Bấm vào một bình luận** (hoặc nút ✎ Chỉnh riêng) thì cột phải hiện bảng chỉnh riêng cho bình luận đó:
     - lời đọc và **giọng đọc**, có nút nghe thử;
     - **sound effect** sau khi đọc xong và lúc xuất hiện, có nút ▶ để nghe;
     - **sticker** và **GIF**: chọn từ lưới ảnh thu nhỏ, kèm vị trí và kích thước. Chúng hiện ra đúng lúc đọc xong (cùng lúc với sound effect), giữ thêm "Giữ GIF/sticker" (mặc định 1,2s) rồi mới qua bình luận sau. Nếu bình luận có video effect thì bình luận tắt cùng lúc với clip;
     - hiệu ứng, vị trí, kích thước và thời lượng;
     - **video effect** (xem phần dưới).
   - Nút ◀ ▶ trong bảng dùng để chuyển giữa các bình luận.
   - Trên mỗi thẻ có nhãn tóm tắt những gì đã chỉnh riêng (🎙 🔊 😀 🎞).
   - Tab **Cài đặt cả video** chứa các giá trị mặc định cho mọi bình luận.
   - Sticker, GIF và âm thanh "ngẫu nhiên" được cố định theo từng bình luận, nên preview và video xuất ra luôn giống nhau.
   - Đổi thứ tự ảnh bằng cách kéo thả hoặc dùng nút ▲▼.
   - Kéo trực tiếp ảnh trên khung preview để đổi vị trí.
   - Cột bên phải chứa giọng đọc, tốc độ, khoảng nghỉ, hiệu ứng, bố cục, âm lượng, ducking nhạc nền và background.
   - Preview 9:16 **tự cập nhật** khoảng 1 giây sau mỗi thay đổi (lời đọc, giọng, âm thanh, thời lượng…), giữ nguyên vị trí đang xem.
   - Bấm **Xuất preview nhanh** để dựng một file MP4 độ phân giải thấp.
   - Mọi thay đổi được tự động lưu vào `data/projects/<tên content>.json`.
3. Chọn nhiều content rồi bấm **Tạo video**. Tab **Hàng đợi** hiện tiến độ của từng video và của cả hàng đợi, có các nút dừng, tiếp tục và dựng lại video lỗi.

## Hiệu ứng âm thanh

- Sau khi đọc xong mỗi bình luận, tool phát một âm thanh ngẫu nhiên lấy từ `SoundEffects/`.
- Bình luận đầu tiên có thêm một âm thanh lúc xuất hiện, tức là có cả ở đầu lẫn ở cuối.
- Âm thanh "ngẫu nhiên" được cố định theo từng ảnh, nên preview và video xuất ra nghe giống nhau.
- Khoảng lặng ở đầu file sound effect được tự cắt và độ to các file được cân bằng. Giọng đọc Edge TTS cũng được cắt bỏ khoảng 0.2 giây im lặng ở đầu và 0.8 giây ở cuối, nên âm thanh vang lên ngay khi giọng dừng.
- Muốn âm thanh vang lên sớm hơn hoặc muộn hơn: vào **Cài đặt cả video → Hiệu ứng âm thanh → “Chờ trước âm sau khi đọc”** (từ −0.5 đến 1.5 giây).
- Có thể đổi các tuỳ chọn này ở nhóm **Hiệu ứng âm thanh**, hoặc chỉnh riêng trong bảng của từng bình luận. Âm “lúc xuất hiện” được chọn riêng cho một bình luận thì luôn phát.
- Nếu thư mục `SoundEffects/` trống, tool chép vào 5 âm thanh mẫu.

## Tự đọc chữ từ ảnh (OCR)

- Không cần gõ lời đọc. Khi mở một content, hoặc khi tạo video hàng loạt, tool tự đọc chữ trong ảnh cho những bình luận **chưa có lời đọc**. Nội dung bạn đã gõ không bao giờ bị ghi đè.
- Với ảnh chụp bình luận (Facebook, TikTok, YouTube…), tool tự bỏ dòng **tên + giờ** ("Redley Dao · 22h") và hàng nút **Reply / Trả lời / Thích**, chỉ giữ nội dung bình luận. Ảnh bài đăng hoặc caption thì giữ toàn bộ chữ.
- Một số lỗi nhận dạng hay gặp được sửa tự động: `12Ok` → `120k`, `vỎ` → `vỏ`, emoji bị đọc thành `""`. Lỗi dấu (ví dụ `rữa`/`rửa`) thì vẫn nên đọc lại và sửa tay.
- Nút **🔤 Đọc chữ** trên mỗi thẻ đọc lại ảnh đó (thay nội dung hiện tại).
- Dùng EasyOCR, chạy offline trên CPU. Lần đầu tool tải model khoảng 100MB, nạp model mất khoảng 12 giây, sau đó mỗi ảnh mất 1–2 giây.
- Tắt hoặc bật tại **Cài đặt → “Tự đọc chữ từ ảnh khi chưa có lời đọc”**.

## Video effect

- Mỗi bình luận chọn được một clip trong `VideoEffects/`. Clip phát **ngay sau khi đọc xong**, có tiếng; nhạc nền tự giảm khi clip phát.
- Bình luận được giữ trên màn hình đến khi clip hết, rồi mới sang bình luận tiếp theo. Thời lượng clip được cộng vào video.
- **Cắt clip** trong bảng của bình luận:
  - kéo thanh "Bắt đầu" và "Kết thúc";
  - hoặc tua trình phát nhỏ đến chỗ muốn cắt, rồi bấm "⇤ Đầu tại đây" hoặc "⇥ Cuối tại đây".
- **Đổi vị trí** bằng cách kéo clip trên khung preview. Chỉnh được kích thước và âm lượng của clip.
- Ở "Cài đặt cả video" có mục **"Dài tối đa"**: giới hạn độ dài mọi clip (hữu ích khi chọn clip ngẫu nhiên).
- Nếu cùng lúc có sound effect "Sau khi đọc xong", hai âm thanh phát chồng lên nhau. Muốn chỉ có tiếng clip thì đặt sound effect của bình luận đó là "Không".

## Ghi chú

- **Giọng đọc** dùng Microsoft Edge TTS: miễn phí, có giọng tiếng Việt (Hoài My, Nam Minh) và cần Internet. Máy chủ Edge đôi khi từ chối một yêu cầu ngẫu nhiên, nên ứng dụng tự thử lại vài lần. Nếu vẫn lỗi, ứng dụng báo lỗi rõ ràng cho content đó và tiếp tục với các content khác. Audio được cache, nên chỉ tạo lại khi lời đọc, giọng hoặc tốc độ thay đổi.
- Thời lượng mỗi ảnh tự căn theo giọng đọc: trễ đầu + độ dài giọng + khoảng nghỉ + hiệu ứng ra. Vì vậy ảnh không bao giờ biến mất trước khi đọc xong.
- Video được ghi vào file `.part.mp4` và chỉ đổi sang tên thật khi FFmpeg chạy thành công. File trùng tên được thêm hậu tố ` (2)`, không bao giờ ghi đè.
- Mã nguồn backend nằm trong `maker/` (FastAPI, bộ dựng, TTS, hàng đợi); giao diện nằm trong `web/`. Công thức hiệu ứng có ở cả `maker/effects.py` và `web/effects.js`; khi sửa thì sửa cả hai để preview khớp với video xuất ra.
