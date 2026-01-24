select Message {
  graphic: { binary, size },
  sender: { id, username },
  recipient: { id, username },
  sent_at
}
order by .sent_at desc
limit 1
