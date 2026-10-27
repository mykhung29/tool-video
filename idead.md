# Xây dựng Local Video Maker Tool tự động dựng video TikTok / Shorts

Hãy xây dựng một công cụ chạy trực tiếp trên máy tính Windows, giúp tự động tạo video TikTok, YouTube Shorts và Reels từ các tài nguyên tôi đã chuẩn bị sẵn.

Mục tiêu là giao diện đơn giản, hiện đại, dễ sử dụng và có khả năng xử lý hàng loạt content mà không phải dựng từng video thủ công.

## 1. Quản lý thư mục đầu vào

Tool sử dụng hai thư mục nguồn chính:

**Folder Backgrounds:** Chứa các video nền tôi đã chuẩn bị sẵn. Mỗi lần tạo video, tool tự động chọn ngẫu nhiên một video trong folder. Có tùy chọn hạn chế sử dụng trùng background liên tiếp và cho phép đổi background thủ công.

**Folder Contents:** Chứa nhiều folder con, mỗi folder con tương ứng với một content và một video cần tạo.

Ví dụ:

```text
VideoMaker/
├── Backgrounds/
│   ├── gameplay_01.mp4
│   ├── gameplay_02.mp4
│   └── gameplay_03.mp4
│
├── Contents/
│   ├── 001_Chuyen_cong_so/
│   │   ├── 01.png
│   │   ├── 02.png
│   │   └── 03.png
│   │
│   ├── 002_Chuyen_tinh_cam/
│   │   ├── 01.png
│   │   ├── 02.png
│   │   └── 03.png
│
└── Output/
```

Tên folder con dùng để đánh dấu và phân biệt từng content. Các ảnh bên trong là những hình ảnh bình luận đã được tôi chuẩn bị sẵn.

Tool tự động quét các folder con, nhận diện ảnh, sắp xếp theo tên file và hiển thị danh sách content. Khi có content mới, tôi chỉ cần thêm folder vào thư mục Contents và làm mới danh sách.

Tôi sẽ tự tìm chủ đề, bài đăng, lựa chọn bình luận và chuẩn bị ảnh. Tool không cần AI tìm kiếm chủ đề, thu thập bài đăng hoặc tự chọn bình luận.

## 2. Giao diện quản lý content

Hiển thị danh sách content với các thông tin:

- Tên content.
- Số lượng ảnh.
- Trạng thái dựng video.
- Background được chọn.
- Trạng thái xử lý hoặc lỗi.

Cho phép chọn một hoặc nhiều content, chọn tất cả, bỏ chọn và tạo video hàng loạt.

Mỗi content tương ứng với một video đầu ra riêng biệt. Tên video mặc định dựa trên tên folder content.

## 3. Nội dung đọc và giọng nói

Mỗi ảnh bình luận là một phân đoạn trong video.

Cho phép nhập nội dung cần đọc tương ứng với từng ảnh, sau đó sử dụng tính năng chuyển văn bản thành giọng nói để tạo giọng đọc tự nhiên.

Các tùy chọn cần có:

- Chọn giọng đọc, tốc độ và âm lượng.
- Nghe thử giọng đọc trước khi dựng.
- Chỉnh sửa nội dung đọc cho từng ảnh.
- Tùy chọn không đọc một số ảnh.
- Điều chỉnh khoảng nghỉ giữa các bình luận.
- Tự động căn thời lượng hiển thị ảnh theo thời lượng giọng đọc.
- Lưu lại nội dung và cấu hình để lần sau không phải nhập lại.

Nếu cần sử dụng dịch vụ TTS bên ngoài, hãy thiết kế phần cài đặt phù hợp và thông báo rõ ràng khi thiếu cấu hình hoặc xảy ra lỗi.

## 4. Hiệu ứng cho ảnh bình luận

Cung cấp nhiều hiệu ứng đẹp, hiện đại và phù hợp với video ngắn, chẳng hạn:

- Pop-in, slide-up, slide-in.
- Fade-in, zoom-in.
- Spring hoặc bounce.
- Highlight và hiệu ứng nhấn mạnh bình luận.
- Hiệu ứng chuyển cảnh giữa các ảnh.
- Hiệu ứng âm thanh nhẹ khi bình luận xuất hiện.

Có thể đặt hiệu ứng mặc định cho toàn bộ video hoặc chỉnh riêng từng ảnh. Hiệu ứng cần mượt mà, không quá rối mắt và phải đồng bộ với giọng đọc.

## 5. Preview và chỉnh sửa video

Có giao diện xem trước video theo tỷ lệ dọc 9:16.

Cho phép:

- Xem trước từng ảnh và toàn bộ video.
- Thay đổi thứ tự ảnh.
- Chỉnh nội dung đọc, giọng đọc và tốc độ.
- Điều chỉnh thời lượng, vị trí, kích thước và hiệu ứng ảnh.
- Thay đổi background.
- Điều chỉnh âm lượng giọng đọc, nhạc nền và hiệu ứng.
- Lưu dự án để tiếp tục chỉnh sửa sau.

Ưu tiên có chế độ xem trước nhanh để kiểm tra nội dung trước khi xuất video chất lượng đầy đủ.

## 6. Dựng video và xử lý âm thanh

Tool tự động kết hợp background, ảnh bình luận, hiệu ứng, giọng đọc và nhạc nền nếu có.

Yêu cầu:

- Background tự động lặp hoặc xử lý phù hợp nếu ngắn hơn nội dung.
- Crop video nền để phù hợp với khung hình dọc.
- Giọng đọc không bị cắt giữa câu.
- Ảnh không biến mất trước khi giọng đọc kết thúc.
- Âm thanh và hiệu ứng đồng bộ với hình ảnh.
- Nhạc nền có thể tự giảm âm lượng khi giọng đọc xuất hiện.
- Có thể bật hoặc tắt từng loại âm thanh.

Thiết lập xuất video mặc định:

- Tỷ lệ 9:16.
- Độ phân giải 1080 × 1920.
- 30 FPS.
- Định dạng MP4, chất lượng phù hợp để đăng mạng xã hội.

Cho phép tùy chỉnh thư mục đầu ra và quy tắc đặt tên file. Không tự động ghi đè video đã tồn tại.

## 7. Tạo video hàng loạt

Đây là tính năng quan trọng nhất.

Khi tôi chọn nhiều content và nhấn **Tạo video**, tool tự động:

1. Đọc từng folder content.
2. Lấy danh sách ảnh và sắp xếp theo tên.
3. Chọn ngẫu nhiên một video background.
4. Tải cấu hình và nội dung đọc đã lưu.
5. Tạo hoặc sử dụng lại audio đã có.
6. Ghép hình ảnh, background, hiệu ứng và âm thanh.
7. Xuất video vào thư mục Output.
8. Tiếp tục xử lý content tiếp theo.

Hiển thị tiến độ từng video và toàn bộ hàng đợi. Nếu một content gặp lỗi, cần thông báo nguyên nhân và cho phép tiếp tục các content khác mà không phải chạy lại từ đầu.

Cho phép dừng hàng đợi, tiếp tục xử lý và dựng lại riêng những video bị lỗi.

## 8. Lưu cấu hình và trải nghiệm sử dụng

- Tự ghi nhớ đường dẫn các thư mục nguồn.
- Tự cập nhật danh sách content khi có folder mới.
- Lưu nội dung đọc, giọng đọc và hiệu ứng theo từng content.
- Lưu lịch sử background đã sử dụng.
- Cho phép mở lại dự án để chỉnh sửa.
- Có trang cài đặt chung cho các tùy chọn mặc định.
- Giao diện dễ hiểu, hạn chế thao tác rườm rà.
- Báo lỗi rõ ràng, không giả lập trạng thái hoàn thành khi video chưa được tạo thành công.

## 9. Yêu cầu triển khai

Hãy sử dụng những công nghệ phổ biến, ổn định và phù hợp nhất hiện nay để xây dựng ứng dụng local trên Windows. Tự lựa chọn giải pháp phù hợp cho giao diện, xử lý video, lưu cấu hình và tạo giọng đọc; không cần giới hạn vào một công nghệ cụ thể.

Ưu tiên khả năng hoạt động thực tế, dễ bảo trì, dễ mở rộng và xử lý được nhiều video liên tiếp.

Hãy triển khai theo từng giai đoạn, bắt đầu bằng quản lý thư mục và content, tiếp đến là dựng video cơ bản, tích hợp giọng đọc, bổ sung hiệu ứng, rồi hoàn thiện preview và tạo video hàng loạt.

Không tự động đăng video lên mạng xã hội. Hãy tập trung xây dựng một công cụ hoàn chỉnh để tôi có thể chuẩn bị tài nguyên, nhấn tạo video và nhận được các video thành phẩm trong thư mục Output.