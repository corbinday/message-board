select Message {
  id,
  graphic_binary := .graphic.binary,
  graphic_size := .graphic.size,
  graphic_frames := .graphic[is PixelAnimation].frames ?? <int16>1,
  graphic_fps := .graphic[is PixelAnimation].fps ?? <int16>10,
  sender_username := .sender.username,
  sender_id := .sender.id
}
filter .id = <uuid>$message_id
limit 1
