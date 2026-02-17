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
    fps := [is PixelAnimation].fps ?? <int16>10
  }
}
filter .recipient = user
order by .sent_at desc
offset <int64>$offset
limit <int64>$limit
