// Opt-in guest framebuffer readback through the native presenter's public API.
// These are game output images, not desktop/window screenshots.
#include <array>
#include <cstdint>
#include <fstream>
#include <filesystem>
#include <rex/ui/presenter.h>
#include <vector>

bool Ch2k8SaveOutput(rex::ui::Presenter *presenter, const char *path) {
  rex::ui::RawImage image;
  if (!presenter || !presenter->CaptureGuestOutput(image) || !image.width ||
      !image.height || image.width > 8192 || image.height > 8192 ||
      image.stride < size_t(image.width) * 4 ||
      image.data.size() < (image.height - 1) * image.stride + image.width * 4)
    return false;
  // Top-down 32-bit BI_RGB BMP. Explicit little-endian fields and BGRA rows.
  std::array<uint8_t, 54> header{};
  auto le = [&](size_t offset, uint32_t value, size_t bytes = 4) {
    for (size_t i = 0; i < bytes; ++i)
      header[offset + i] = uint8_t(value >> (i * 8));
  };
  const uint32_t bytes = image.width * image.height * 4;
  header[0] = 'B';
  header[1] = 'M';
  le(2, bytes + 54);
  le(10, 54);
  le(14, 40);
  le(18, image.width);
  le(22, uint32_t(-int32_t(image.height)));
  le(26, 1, 2);
  le(28, 32, 2);
  le(34, bytes);
  std::ofstream output(std::filesystem::u8path(path), std::ios::binary);
  if (!output)
    return false;
  output.write(reinterpret_cast<const char *>(header.data()), header.size());
  std::vector<uint8_t> row(size_t(image.width) * 4);
  for (uint32_t y = 0; y < image.height; ++y) {
    const auto *source = image.data.data() + y * image.stride;
    for (uint32_t x = 0; x < image.width; ++x) {
      row[x * 4] = source[x * 4 + 2];
      row[x * 4 + 1] = source[x * 4 + 1];
      row[x * 4 + 2] = source[x * 4];
      row[x * 4 + 3] = 0;
    }
    output.write(reinterpret_cast<const char *>(row.data()), row.size());
  }
  output.close();
  return bool(output);
}
