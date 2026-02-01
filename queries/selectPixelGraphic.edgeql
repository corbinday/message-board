with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  )
select PixelGraphic {
  id,
  binary,
  size,
  created_at,
  updated_at
}
filter .id = <uuid>$graphic_id
  # Allow viewing if creator OR recipient of a message containing it?
  # For now just creator or global lookup (since messages are shared)
  # But technically PixelGraphic has a required creator.
  # Let's just filter by ID for serving images, maybe with basic auth check if needed.
  # But for now, let's keep it simple.
  limit 1
