with
  user := assert_single(
    select User
    filter global ext::auth::ClientTokenIdentity in .identity
  )
select Message {
  id,
  sent_at,
  is_read,
  sender: { id, username },
  recipient: { id, username },
  graphic: {
    id,
    size,
    frames := [is PixelAnimation].frames ?? <int16>1,
    frame_delay_ms := [is PixelAnimation].frame_delay_ms ?? <int16>100
  }
}
filter .recipient = user
order by .sent_at desc
offset <int64>$offset
limit <int64>$limit
