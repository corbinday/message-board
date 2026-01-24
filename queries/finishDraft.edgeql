# Finish a draft by converting it to either StaticImage or PixelAnimation
# based on whether frames > 1
with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  ),
  draft := assert_single(
    select DraftGraphic
    filter .id = <uuid>$draft_id
      and .creator = user
  ),
  # Pre-compute to avoid correlated set issue
  is_animation := draft.frames > 1,
  new_graphic := (
    insert PixelAnimation {
      binary := draft.binary,
      frames := draft.frames,
      frame_delay_ms := draft.frame_delay_ms,
      size := draft.size,
      creator := user
    }
  ) if is_animation else (
    insert StaticImage {
      binary := draft.binary,
      size := draft.size,
      creator := user
    }
  )
select {
  graphic := new_graphic { id },
  deleted := (delete draft)
}
